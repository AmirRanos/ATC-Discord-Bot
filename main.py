import discord
import os
import asyncio
from gtts import gTTS

class Voice_Provider:
	def say(self, msg):
		raise NotImplementedError()

	def sanitize(self, string):
		retval = []
		for c in string:
			if c.lower() in 'abcdefghijklmnopqrstuvwxyz0123456789 ,.?!':
				retval.append(c)
		return ''.join(retval)
		
class Festival_Voice(Voice_Provider):
	def say(self, msg):
		output_fname = 'voice.wav'
		command = 'echo "{}" | text2wave -eval "(voice_cmu_us_slt_arctic_hts)" -o {}'.format(self.sanitize(msg), output_fname)
		os.system(command)
		return output_fname
		
class GTTS_Voice(Voice_Provider):
	def say(self, msg):
		output_fname = 'voice.wav'
		tts = gTTS(self.sanitize(msg))
		tts.save(output_fname)
		return output_fname
		
class Pico_Voice(Voice_Provider):
	def say(self, msg):
		output_fname = 'voice.wav'
		command = 'pico2wave -w {} "{}"'.format(output_fname, self.sanitize(msg))
		os.system(command)
		return output_fname

class Echo_Bot(discord.Client):
	
	def __init__(self, controller, voice_provider=Festival_Voice()):
		self.controller = controller
		self.voice_provider = voice_provider
		super().__init__()
	
	async def on_ready(self):
		print('Logged in as {}'.format(self.user))
		
	async def on_message(self, message):
		if message.author.bot:
			return
			
		if message.content.startswith('`atc'):
			await self.join_voice_channel(message.author.voice.channel)
		if message.content.startswith('`akill'):
			await self.logout()

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
			
			ofname = self.voice_provider.say(message)
			bot_client.play(discord.FFmpegOpusAudio(ofname))

	async def join_voice_channel(self, voice_channel):
		voice_client = voice_channel.guild.voice_client
		if voice_client is None or voice_client.channel != voice_channel:
			try:
				voice_client = await voice_channel.connect()
			except discord.client.ClientException as e:
				pass
		return voice_client

class Echo_Bot_Controller:
	
	def __init__(self, tokens):
		self.tokens = tokens
		self.running = True
		
	async def run(self):
		await asyncio.gather(*[self.handle_one_bot(token) for token in self.tokens])
		
	async def handle_one_bot(self, token):
		while self.running:
			print('Starting worker bot...')
			bot = Echo_Bot(self)
			await bot.start(token)
		

async def main():
	tokens = []
	with open('tokens.txt') as f:
		token = f.readline().strip()
		tokens.append(token)
		
	bot_controller = Echo_Bot_Controller(tokens)
	await bot_controller.run()

if __name__ == '__main__':
	asyncio.run(main())
