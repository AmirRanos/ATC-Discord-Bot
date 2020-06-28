#!/usr/bin/env python

import discord
import os
import random
import asyncio
import os.path
from gtts import gTTS

DEFAULT_VOICE_NAME = 'festival'

class Voice_Provider:
	def say(self, msg):
		raise NotImplementedError()

	def get_temp_output_filename(self):
		temp_dir = 'temp'
		create_folder_if_none_exists(temp_dir)
		return os.path.join(temp_dir, 'voice_{}.wav'.format(random.randint(0, 9999999)))
	
	def get_cached_output_filename(self, msg):
		retval = []
		msg = msg.lower()
		for c in msg:
			if c in 'abcdefghijklmnopqrstuvwxyz ':
				retval.append(c)
		return ''.join(retval)
		
	def cache_voice(self, directory, messages):
		create_folder_if_none_exists(directory)
		
		for msg in messages:
			cached_fname = os.path.join(directory, '{}.wav'.format(self.get_cached_output_filename(msg)))
			self.generate_wave(msg, cached_fname)

	def sanitize(self, string):
		retval = []
		for c in string:
			if c.lower() in 'abcdefghijklmnopqrstuvwxyz0123456789 ,.?!':
				retval.append(c)
		return ''.join(retval)
	
	def say(self, msg):
		output_fname = self.get_temp_output_filename()
		return self.generate_wave(msg, output_fname)
		
	def generate_wave(self, msg, output_fname):
		raise NotImplementedError()
		
class Festival_Voice(Voice_Provider):
		
	def generate_wave(self, msg, output_fname):
		msg = self.sanitize(msg)
		command = 'echo "{}" | text2wave -eval "(voice_cmu_us_slt_arctic_hts)" -o {}'.format(msg, output_fname)
		os.system(command)
		return output_fname
		
class GTTS_Voice(Voice_Provider):
		
	def generate_wave(self, msg, output_fname):
		msg = self.sanitize(msg)
		tts = gTTS(msg)
		tts.save(output_fname)
		return output_fname
		
class Pico_Voice(Voice_Provider):
		
	def generate_wave(self, msg, output_fname):
		msg = self.sanitize(msg)
		command = 'pico2wave -w {} "{}"'.format(output_fname, msg)
		os.system(command)
		return output_fname

class Custom_Voice(Voice_Provider):
	
	def __init__(self, file_dir, fallback):
		self.file_dir = file_dir
		self.fallback = fallback
	
	def say(self, msg):
		msg = self.sanitize(msg)
		custom_fname = os.path.join(self.file_dir, '{}.wav'.format(self.get_cached_output_filename(msg)))
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
		
		cmd_args = message.content.split(' ')
		cmd_args = [x for x in cmd_args if len(x) > 0]
		
		if len(cmd_args) >= 1 and cmd_args[0] == '`atc':
			
			cmd = 'join'
			
			if len(cmd_args) >= 2:
				commands = ['shutdown', 'join', 'voice', 'leave']
				if cmd_args[1].lower() in commands:
					cmd = cmd_args[1]
			
			if cmd == 'shutdown':
				await self.controller.on_cmd_shutdown(message, cmd_args)
			elif cmd == 'voice':
				await self.controller.on_cmd_voice_change(message, cmd_args)
			elif cmd == 'join':
				await self.on_cmd_join(message, cmd_args)
			elif cmd == 'leave':
				await self.on_cmd_leave(message, cmd_args)
		
	async def on_cmd_join(self, message, cmd_args):
		# Do not respond if already in use
		if self.check_is_active():
			return
		voice_channel = message.author.voice.channel
		bot_already_connected = self.controller.get_bot_already_connected(voice_channel)
		if bot_already_connected is None:
			await self.join_voice_channel(message.author.voice.channel)
			await self.announce_misc(message.author.voice.channel, 'ATC Online')
			await self.send_message(message.channel, 'Hello!')
		
	async def on_cmd_leave(self, message, cmd_args):
		voice_channel = message.author.voice.channel
		relevant = False
		for client in self.voice_clients:
			if voice_channel == client.channel:
				relevant = True
				break
				
		if not relevant:
			return
		
		await self.announce_misc(message.author.voice.channel, 'ATC going offline', wait_until_finished=True)
		await self.leave_voice_channel(message.author.voice.channel)
		await self.send_message(message.channel, 'Goodbye!')

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
				else:
					# Not relevant for us
					return
		else:
			return
				
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
			
	async def announce_misc(self, voice_channel, msg_text, wait_until_finished=False):
		voice_client = None
		for vc in self.voice_clients:
			if vc.guild == voice_channel.guild:
				voice_client = vc
		if voice_client is not None:
			try:
				ofname = self.voice_provider.say(msg_text)
				
				
				if wait_until_finished:
					print('Waiting until we finish saying: {}'.format(msg_text))
					finished = False
					def after(err):
						nonlocal finished
						print('Done saying: {}'.format(msg_text))
						finished = True
					voice_client.play(discord.FFmpegOpusAudio(ofname), after=after)
					while not finished:
						await asyncio.sleep(0.1)
				else:
					voice_client.play(discord.FFmpegOpusAudio(ofname))
			except discord.errors.ClientException as e:
				print('Error occured while announcing message {}: {}'.format(msg_text, e.what()))
				pass
		else:
			print('Could not find voice channel in collectionfor message {}: {}'.format(msg_text, voice_channel.id))
		

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

	async def leave_voice_channel(self, voice_channel, force=False):
		voice_client = None
		for vc in self.voice_clients:
			if vc.guild == voice_channel.guild:
				voice_client = vc
		if voice_client is not None and voice_client.channel == voice_channel:
			try:
				await voice_client.disconnect(force=force)
			except discord.client.ClientException as e:
				print('Error trying to disconnect: {}'.format(e.what()))
				return False
				
		return True
		
	async def send_message(self, text_channel, msg):
		
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
	
	def __init__(self, config):
		self.config = config
		self.running = True
		self.voice_provider = make_voice_from_name(self.config.voice_selection)
		self.worker_bots = {}
		
	async def run(self):
		await asyncio.gather(*[self.handle_one_bot(token) for token in self.config.tokens])
		
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
		
	async def on_cmd_shutdown(self, message, cmd_args):
		if message.author.id not in self.config.admin_ids:
			return
		await self.shutdown()
		
	async def on_cmd_voice_change(self, message, cmd_args):
		if message.author.id not in self.config.admin_ids:
			return
		voice = DEFAULT_VOICE_NAME
		if len(cmd_args) >= 3:
			voice = cmd_args[2].lower()
		
		self.config.voice_selection = voice
		self.config.save_config()
		self.voice_provider = make_voice_from_name(self.config.voice_selection)
		
		for token, bot in self.worker_bots.items():
			bot.voice_provider = self.voice_provider
			
		# Done after we set the voice providers
		# In order to ensure that the update reaches all bots
		for token, bot in self.worker_bots.items():
			await bot.announce_misc(message.author.voice.channel, 'ATC Online')
		
class Config:
	
	def __init__(self):
		self.tokens = []
		self.admin_ids = []
		self.voice_selection = DEFAULT_VOICE_NAME
		
	def open_config(self):
		try:
			with open('tokens.txt', 'r') as f:
				tokens = f.readlines()
				tokens = [x.strip() for x in tokens]
				tokens = [x for x in tokens if len(x) > 0]
				self.tokens = tokens
		except FileNotFoundError:
			print('Warn: could not find tokens.txt')
		
		try:
			with open('admins.txt', 'r') as f:
				admin_ids = f.readlines()
				admin_ids = [x.strip() for x in admin_ids]
				admin_ids = [int(x) for x in admin_ids if len(x) > 0]
				self.admin_ids = admin_ids
		except FileNotFoundError:
			print('Warn: could not find admins.txt')
		
		try:
			with open('voice.txt', 'r') as f:
				voice_id = f.readlines()
				voice_id = [x.strip() for x in voice_id]
				voice_id = voice_id[0]
				self.voice_selection = voice_id
		except FileNotFoundError:
			print('Warn: could not find voice.txt')
		
	def save_config(self):
		with open('tokens.txt', 'w+') as f:
			for x in self.tokens:
				f.write('{}\n'.format(x))
		with open('admins.txt', 'w+') as f:
			for x in self.admin_ids:
				f.write('{}\n'.format(x))
		with open('voice.txt', 'w+') as f:
			f.write(self.voice_selection + '\n')
	
def make_voice_from_name(name):
	name = name.lower()
	if name == 'festival':
		return Festival_Voice()
	elif name == 'pico':
		return Pico_Voice()
	elif name == 'gtts':
		return GTTS_Voice()
	else:
		return Custom_Voice(name, Festival_Voice())
		
def create_folder_if_none_exists(folder_dir):
	if not os.path.exists(folder_dir):
		os.makedirs(folder_dir)

async def main():
	
	config = Config()
	config.open_config()
	config.save_config()
		
	print('Tokens: {}'.format(len(config.tokens)))
	print('Admins: {}'.format(config.admin_ids))
	
	if len(config.tokens) == 0:
		print('Error: At least one bot token must be provided in tokens.txt')
		return
		
	bot_controller = Echo_Bot_Controller(config)
	await bot_controller.run()

if __name__ == '__main__':
	asyncio.run(main())
