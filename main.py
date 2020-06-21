import discord
import os
from gtts import gTTS


class Echo_Bot(discord.Client):
	
	async def on_ready(self):
		print('Logged in as {}'.format(self.user))
		
	async def on_message(self, message):
		if message.author.bot:
			return
			
		if message.content.startswith('`atc'):
			await join_voice_channel(self, message.author.voice.channel)

	async def on_voice_state_update(self, member, before, after):
		print(member, before.channel, after.channel)
		
		announce = None
		
		bot_client = member.guild.voice_client
		if bot_client is not None:
			if after.channel != before.channel:
				if after.channel == bot_client.channel:
					announce = 'join'
				elif before.channel == bot_client.channel:
					announce = 'leave'
				
		if announce is not None:
			message = ''
			display_name = member.display_name
			if member.bot:
				display_name = 'service droid'
			if announce == 'join':
				message = 'Welcome {}.'.format(display_name)
			elif announce == 'leave':
				message = 'Goodbye {}.'.format(display_name)
			
			ofname = 'voice.wav'
			make_voice_festival(ofname, message)
			bot_client.play(discord.FFmpegOpusAudio(ofname))

	

def sanitize(string):
	retval = []
	for c in string:
		if c.lower() in 'abcdefghijklmnopqrstuvwxyz0123456789 ,.?!':
			retval.append(c)
	return ''.join(retval)

def make_voice_pico(output_fname, msg):
	command = 'pico2wave -w {} "{}"'.format(output_fname, sanitize(msg))
	os.system(command)
	
def make_voice_festival(output_fname, msg):
	command = 'echo "{}" | text2wave -eval "(voice_cmu_us_slt_arctic_hts)" -o {}'.format(sanitize(msg), output_fname)
	os.system(command)

def make_voice_gtts(output_fname, msg):
	tts = gTTS(msg)
	tts.save(output_fname)

async def join_voice_channel(client, voice_channel):
	voice_client = voice_channel.guild.voice_client
	if voice_client is None or voice_client.channel != voice_channel:
		try:
			voice_client = await voice_channel.connect()
		except discord.client.ClientException as e:
			pass
	return voice_client

if __name__ == '__main__':
	with open('token.txt') as f:
		token = f.readline().strip()
	client = Echo_Bot()
	client.run(token)
