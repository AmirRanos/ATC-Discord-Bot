#!/usr/bin/env python

import discord
import os
import random
import asyncio
import os.path
from gtts import gTTS

class Voice_Provider:
	def say(self, msg):
		raise NotImplementedError()

	def get_output_filename(self):
		return 'voice_{}.wav'.format(random.randint(0, 9999999))

	def sanitize(self, string):
		retval = []
		for c in string:
			if c.lower() in 'abcdefghijklmnopqrstuvwxyz0123456789 ,.?!':
				retval.append(c)
		return ''.join(retval)
		
class Festival_Voice(Voice_Provider):
	def say(self, msg):
		output_fname = self.get_output_filename()
		command = 'echo "{}" | text2wave -eval "(voice_cmu_us_slt_arctic_hts)" -o {}'.format(self.sanitize(msg), output_fname)
		os.system(command)
		return output_fname
		
class GTTS_Voice(Voice_Provider):
	def say(self, msg):
		output_fname = self.get_output_filename()
		tts = gTTS(self.sanitize(msg))
		tts.save(output_fname)
		return output_fname
		
class Pico_Voice(Voice_Provider):
	def say(self, msg):
		output_fname = self.get_output_filename()
		command = 'pico2wave -w {} "{}"'.format(output_fname, self.sanitize(msg))
		os.system(command)
		return output_fname

class Custom_Voice(Voice_Provider):
	def __init__(self, file_dir, fallback):
		self.file_dir = file_dir
		self.fallback = fallback
	
	def get_fname(self, msg):
		retval = []
		msg = msg.lower()
		for c in msg:
			if c in 'abcdefghijklmnopqrstuvwxyz ':
				retval.append(c)
		return ''.join(retval)
	
	def say(self, msg):
		custom_fname = os.path.join(self.file_dir, '{}.wav'.format(self.get_fname(self.sanitize(msg))))
		print(custom_fname)
		if os.path.exists(custom_fname):
			return custom_fname
		else:
			return self.fallback.say(msg)

class Greeter_Queue:
	
	def __init__(self):
		self._queue = []
		
	def _erase_element(self, elem):
		self._queue = [x for x in self._queue if x != elem]
		
	def pop_front(self):
		if len(self._queue) == 0:
			return None
		
		return ''.join(self._queue.pop(0))
		
	def peek_front(self):
		if len(self._queue) == 0:
			return None
		
		return ''.join(self._queue[0])
		
	def clear_all(self):
		self._queue.clear()
		
	def add_welcome(self, name):
		self._erase_element(('Goodbye ', name))
		self._queue.append(('Welcome ', name))
		
	def add_goodbye(self, name):
		self._erase_element(('Welcome ', name))
		self._queue.append(('Goodbye ', name))
	
			

class Echo_Bot(discord.Client):
	
	def __init__(self, controller, voice_provider, priority=0):
		self.priority = priority
		self.controller = controller
		self.voice_provider = voice_provider
		self.greeter_queue = Greeter_Queue()
		super().__init__()
	
	async def on_ready(self):
		print('Logged in as {}'.format(self.user))
		
	async def on_message(self, message):
		if message.author.bot:
			return
		
		await self.controller.on_message(message)

	async def _process_greeter_queue(self, voice_client):
		while self.greeter_queue.peek_front() is not None:
			message = self.greeter_queue.peek_front()
			while voice_client.is_playing():
				await asyncio.sleep(0.1)
			
			nobody_there = all(x.bot for x in voice_client.channel.members)
			if nobody_there:
				self.greeter_queue.clear_all()
				print('Clearing queue since nobody is there to hear anything')
			else:
				ofname = self.voice_provider.say(message)
				try:
					voice_client.play(discord.FFmpegOpusAudio(ofname))
					self.greeter_queue.pop_front()
				except discord.errors.ClientException:
					await asyncio.sleep(0.1)
					

	async def on_voice_state_update(self, member, before, after):
		print(member, before.channel, after.channel)
		
		self.priority -= 1
		
		if member == self.user:
			# Clear out queue if moving to a different channel
			if after.channel != before.channel:
				self.greeter_queue.clear_all()
			print('Not greeting self')
			return
		
		announce = None
		
		voice_client = member.guild.voice_client
		if voice_client is not None:
			if after.channel != before.channel:
				if after.channel == voice_client.channel:
					announce = 'join'
				elif before.channel == voice_client.channel:
					announce = 'leave'
				
		if announce is not None:
			message = ''
			display_name = member.display_name
			if member.bot:
				display_name = 'service droid'
				
			
			if announce == 'join':
				self.greeter_queue.add_welcome(display_name)
			elif announce == 'leave':
				self.greeter_queue.add_goodbye(display_name)
			
			# Adding a bit of delay to when ATC starts talking.
			# Note that this intentionally does not add a delay
			# between what is said while emptying the queue of voices
			await asyncio.sleep(1)
				
			await self._process_greeter_queue(voice_client)
			
	async def external_announce_self(self, voice_channel):
		voice_client = voice_channel.guild.voice_client
		ofname = self.voice_provider.say('Hello world')
		voice_client.play(discord.FFmpegOpusAudio(ofname))
		

	async def external_join_voice_channel(self, voice_channel):
		
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
		
	async def external_send_message(self, text_channel, msg):
		
		text_channel = self.get_channel(text_channel.id)
		if text_channel is None:
			raise RuntimeError('Cannot find channel with ID: {}'.format(text_channel.id))
		
		if not isinstance(text_channel, discord.TextChannel):
			raise RuntimeError('No text channel with ID: {}'.format(text_channel.id))
			
		await text_channel.send(msg)
		
	def check_is_active(self):
		if len(self.voice_clients) == 0:
			return False
		else:
			for client in self.voice_clients:
				channel = client.channel
				for member in channel.members:
					if not member.bot:
						return True
			return False

class Echo_Bot_Controller:
	
	def __init__(self, tokens, voice_provider, admins):
		self.tokens = tokens
		self.voice_provider = voice_provider
		self.running = True
		self.worker_bots = {}
		self.admins = admins
		
	async def run(self):
		await asyncio.gather(*[self.handle_one_bot(token) for token in self.tokens])
		
	async def handle_one_bot(self, token):
		while self.running:
			try:
				print('Starting worker bot...')
				bot = Echo_Bot(self, self.voice_provider)
				self.worker_bots[token] = bot
				
				async def bot_restarter():
					while not bot.is_closed() and self.running:
						if not bot.check_is_active():
							if random.randint(0, 60*60) == 0:
								await bot.logout()
								print('Shutdown bot for inactivity')
								break
						await asyncio.sleep(1)
				
				await asyncio.gather(bot.start(token), bot_restarter())
			except RuntimeError as e:
				print(e.what)
			
	def get_bot_with(self, checker):
		'''
		Get the bot with the highest priority that passes checker()
		
		or None if none exists
		'''
		
		best_bot = None
		best_priority = None
		for _, bot in self.worker_bots.items():
			if not bot.is_closed() and checker(bot):
				if best_bot is None or bot.priority > best_priority:
					best_priority = bot.priority
					best_bot = bot
					
		return best_bot
		
	def get_bot_already_connected(self, voice_channel):
		'''
		Get the bot that is connected to the given voice channel, or None if there isn't one
		'''
		
		def checker(bot):
			return voice_channel in [x.channel for x in bot.voice_clients]
		return self.get_bot_with(checker)
		
	def get_bot_idling(self):
		'''
		Get a bot that is not connected to the given voice channel or is connected to an empty voice channel
		'''
		def checker(bot):
			return not bot.check_is_active()
		
		return self.get_bot_with(checker)
		
	def get_bot_any(self):
		return self.get_bot_with(lambda x: True)
		
	async def shutdown(self):
		self.running = False
		print('Shutting down...')
		for token, bot in self.worker_bots.items():
			await bot.logout()
		
	async def cmd_join(self, message):
		voice_channel = message.author.voice.channel
		
		bot_already_connected = self.get_bot_already_connected(voice_channel)
		if bot_already_connected is None:
			bot = self.get_bot_idling()
			
			if bot is None:
				bot = self.get_bot_any()
				await bot.external_send_message(message.channel, 'No available bots.')
			else:
				await bot.external_join_voice_channel(message.author.voice.channel)
				await bot.external_announce_self(message.author.voice.channel)
				await bot.external_send_message(message.channel, 'Hello!')
		
			
	async def on_message(self, message):
		cmd_args = message.content.split(' ')
		cmd_args = [x for x in cmd_args if len(x) > 0]
		
		if len(cmd_args) >= 1 and cmd_args[0] == '`atc':
			
			cmd = 'join'
			
			if len(cmd_args) >= 2:
				commands = ['shutdown', 'join']
				if cmd_args[1].lower() in commands:
					cmd = cmd_args[1]
			
			if cmd == 'shutdown':
				if message.author.id in self.admins:
					await self.shutdown()
			elif cmd == 'join':
				await self.cmd_join(message)
			
		#if message.content.startswith('`akill'):
		#	await self.logout()
		

async def main():
	tokens = []
	with open('tokens.txt') as f:
		tokens = f.readlines()
		tokens = [x.strip() for x in tokens]
		tokens = [x for x in tokens if len(x) > 0]
		
	admin_ids = []
	with open('admins.txt') as f:
		admin_ids = f.readlines()
		admin_ids = [x.strip() for x in admin_ids]
		admin_ids = [int(x) for x in admin_ids if len(x) > 0]
		
	print('Tokens: {}'.format(len(tokens)))
	print('Admins: {}'.format(admin_ids))
		
	voice_provider = Custom_Voice('custom', Festival_Voice())
		
	bot_controller = Echo_Bot_Controller(tokens, voice_provider, admin_ids)
	await bot_controller.run()

if __name__ == '__main__':
	asyncio.run(main())
