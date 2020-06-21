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
	
	def __init__(self, controller, voice_provider=Festival_Voice(), priority=0):
		self.priority = priority
		self.controller = controller
		self.voice_provider = voice_provider
		super().__init__()
	
	async def on_ready(self):
		print('Logged in as {}'.format(self.user))
		
	async def on_message(self, message):
		if message.author.bot:
			return
		
		await self.controller.on_message(message)

	async def on_voice_state_update(self, member, before, after):
		print(member, before.channel, after.channel)
		
		self.priority -= 1
		
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
		
		voice_client = None
		for vc in self.voice_clients:
			if vc.guild == voice_channel.guild:
				voice_client = vc
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
		self.worker_bots = {}
		
	async def run(self):
		await asyncio.gather(*[self.handle_one_bot(token) for token in self.tokens])
		
	async def handle_one_bot(self, token):
		while self.running:
			print('Starting worker bot...')
			bot = Echo_Bot(self)
			self.worker_bots[token] = bot
			await bot.start(token)
			
	def get_available_bot(self, checker):
		'''
		Get the bot with the highest priority that passes checker()
		
		or None if none exists
		'''
		
		best_bot = None
		best_priority = None
		for _, bot in self.worker_bots.items():
			if checker(bot):
				if best_bot is None or bot.priority > best_priority:
					best_priority = bot.priority
					best_bot = bot
					
		return best_bot
			
	async def on_message(self, message):
		if message.content.startswith('`atc'):
			voice_channel = message.author.voice.channel
			
			bot_already_connected = self.get_available_bot(lambda bot: voice_channel in [x.channel for x in bot.voice_clients])
			if bot_already_connected is None:
				
				bot = self.get_available_bot(lambda bot: len(bot.voice_clients) == 0)
				await bot.join_voice_channel(message.author.voice.channel)
		
		#if message.content.startswith('`akill'):
		#	await self.logout()
		

async def main():
	tokens = []
	with open('tokens.txt') as f:
		tokens = f.readlines()
		tokens = [x.strip() for x in tokens]
		tokens = [x for x in tokens if len(x) > 0]
		
	print('Tokens: {}'.format(len(tokens)))
		
	bot_controller = Echo_Bot_Controller(tokens)
	await bot_controller.run()

if __name__ == '__main__':
	asyncio.run(main())
