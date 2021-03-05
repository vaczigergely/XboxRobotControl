
import servo
import logging
import time
import Adafruit_PCA9685
import RPi.GPIO as GPIO
from evdev import InputDevice, categorize, ecodes, ff
import vg_motor_control
from sh import bluetoothctl
import asyncio
import sys


def grab():
	try:
		pos_input = 0
		OUT = 1
		while 1:
			a=input()
			if OUT == 1:
				if pos_input < 13:
					pos_input+=1
				else:
					print('MAX')
					OUT = 0
			else:
				if pos_input > 1:
					pos_input-=1
				else:
					print('MIN')
					OUT = 1
			servo.catch(pos_input)
			print(pos_input)

			pass
	except KeyboardInterrupt:
		servo.clean_all()


def hand(command, handposition):
	if command == 'in':
		pwm.set_pwm(13, 0, handposition)
		pwm.set_pwm(12, 0, handposition)
		time.sleep(0.5)
		pwm.set_pwm(13, 0, 400)
		pwm.set_pwm(12, 0, 400)
	elif command == 'out':
		pwm.set_pwm(12, 0, handposition)
		pwm.set_pwm(13, 0, handposition)
		logging.debug('Servo {} and {} is set to position {}'.format('12','13','400'))


def vibrate_controller(dev):
	rumble = ff.Rumble(strong_magnitude=0xc000, weak_magnitude=0xc000)
	effect_type = ff.EffectType(ff_rumble_effect=rumble)
	duration_ms = 300
	dev = dev

	effect = ff.Effect(
        ecodes.FF_RUMBLE, # type
        -1, # id (set by ioctl)
        0,  # direction
        ff.Trigger(0, 0), # no triggers
        ff.Replay(duration_ms, 0), # length and delay
        ff.EffectType(ff_rumble_effect=rumble)
    )

	effect_id = dev.upload_effect(effect)
	repeat_count = 1
	dev.write(ecodes.EV_FF, effect_id, repeat_count)
	time.sleep(1)
	dev.erase_effect(effect_id) 


async def checkdist(dev):
	Tr = 11 # Pin number of input terminal of ultrasonic module 
	Ec = 8 # Pin number of output terminal of ultrasonic module
	GPIO.setmode(GPIO.BCM)
	GPIO.setup(Tr, GPIO.OUT,initial=GPIO.LOW) 
	GPIO.setup(Ec, GPIO.IN)

	global allowforward

	while 1:
		try:
			GPIO.output(Tr, GPIO.HIGH) # Set the input end of the module to high level and emit an initial sound wave time.sleep(0.000015)
			GPIO.output(Tr, GPIO.LOW)
			while not GPIO.input(Ec): # When the module no longer receives the initial sound wave 
				pass
			t1 = time.time() # Note the time when the initial sound wave is emitted 
			while GPIO.input(Ec): # When the module receives the return sound wave
				pass
			t2 = time.time() # Note the time when the return sound wave is captured
			if (float(round((t2-t1)*340/2,2))) < 0.40:
				allowforward = False
				vg_motor_control.motorStop()
				vibrate_controller()
				await asyncio.sleep(0.5)
			else:
				allowforward = True
				await asyncio.sleep(0.5)
		except Exception as e:
			allowforward = True
			await asyncio.sleep(1)


async def helper(dev):
	global allowforward
	handposition = 300
	async for event in dev.async_read_loop():
		if event.type == ecodes.EV_KEY:
			print(event)
		#Gamepad analogique | Analog gamepad
		elif event.type == ecodes.EV_ABS:
			absevent = categorize(event)
			#print(ecodes.bytype[absevent.event.type][absevent.event.code], absevent.event.value)
			pushed = ecodes.bytype[absevent.event.type][absevent.event.code], absevent.event.value

			if pushed[0] == "ABS_GAS" and pushed[1] > 10:
				handposition -= 5
				hand("out", handposition)
				time.sleep(0.02)
			elif pushed[0] == "ABS_BRAKE" and pushed[1] > 10:
				handposition += 5
				hand("out", handposition)
				time.sleep(0.02)

			if pushed[0] == "ABS_Y" and pushed[1] >= 0 and pushed[1] < 34440:
				speed_set = 100 - int((pushed[1]/34440) * 100) - 1
				print(speed_set)
				if speed_set > 20:
					vg_motor_control.move(speed_set, 'forward', 'no', 0.0)
					await asyncio.sleep(0)
				else:
					vg_motor_control.motorStop()
			elif pushed[0] == "ABS_Y" and pushed[1] >= 34440:
				speed_set = (100 - int((pushed[1]/34440) * 100)) * -1
				print(speed_set)	
				if speed_set > 20:
					vg_motor_control.move(speed_set, 'backward', 'no', 0.0)
				else:
					vg_motor_control.motorStop()
			elif pushed[0] == "ABS_Z" and pushed[1] >= 51000:
				vg_motor_control.move(100, 'no', 'right', 0.0)
				time.sleep(0.02)
				vg_motor_control.motorStop()
			elif pushed[0] == "ABS_Z" and pushed[1] < 10000:
				vg_motor_control.move(100, 'no', 'left', 0.0)
				time.sleep(0.02)
				vg_motor_control.motorStop()
	
	vg_motor_control.motorStop()
	


if __name__ == '__main__':

	logging.basicConfig(format='%(asctime)s %(levelname)-8s %(message)s', datefmt='%Y-%m-%d %H:%M:%S', filename='vg_servo.log', level=logging.INFO)

	pwm = Adafruit_PCA9685.PCA9685()
	pwm.set_pwm_freq(50)

	servo.initPosAll()
	print('All servos are in initial position')
	logging.info('All servos are in initial position')
	time.sleep(1)

	try:
		mac = "9C:AA:1B:A7:63:E5"
		bluetoothctl("connect", mac)
		time.sleep(5)
	except Exception as e:
		pass

	gamepad = InputDevice('/dev/input/event0')
	dev = gamepad
	vibrate_controller(dev)

	vg_motor_control.setup()
	allowforward = True

	loop = asyncio.get_event_loop()
	coroutine1 = helper(dev)
	coroutine2 = checkdist(dev)
	task1 = loop.create_task(coroutine1)
	task2 = loop.create_task(coroutine2)
	loop.run_until_complete(asyncio.wait([task1, task2]))