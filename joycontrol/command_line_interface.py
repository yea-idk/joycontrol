import inspect
import logging
import pygame
import asyncio

from aioconsole import ainput

from joycontrol.controller_state import button_push, ControllerState
from joycontrol.transport import NotConnectedError

pygame.init()
joysticks = []
clock = pygame.time.Clock()
keepPlaying = True

logger = logging.getLogger(__name__)

button_map = {
            0: 'b', #        cross    b
            1: 'a', #        circle   a
            2: 'y', #        square   y
            3: 'x', #        triangle x
            4: 'l', #        l1       l
            5: 'r', #        r1       r
            6: 'zl', #       l2       zl
            7: 'zr', #       r2       zr
            8: 'minus', #    share    -
            9: 'plus', #     options  +
            10: 'home', #    ps       home
            11: 'l_stick', # l3       stick 1
            12: 'r_stick', # r3       stick 2
        }

def pygame_event_loop(loop, event_queue):
    while True:
        event = pygame.event.wait()
        asyncio.run_coroutine_threadsafe(event_queue.put(event), loop=loop)

def _print_doc(string):
    """
    Attempts to remove common white space at the start of the lines in a doc string
    to unify the output of doc strings with different indention levels.

    Keeps whitespace lines intact.

    :param fun: function to print the doc string of
    """
    lines = string.split('\n')
    if lines:
        prefix_i = 0
        for i, line_0 in enumerate(lines):
            # find non empty start lines
            if line_0.strip():
                # traverse line and stop if character mismatch with other non empty lines
                for prefix_i, c in enumerate(line_0):
                    if not c.isspace():
                        break
                    if any(lines[j].strip() and (prefix_i >= len(lines[j]) or c != lines[j][prefix_i])
                           for j in range(i+1, len(lines))):
                        break
                break

        for line in lines:
            print(line[prefix_i:] if line.strip() else line)

class ControllerCLI:
    def __init__(self, controller_state: ControllerState):
        self.controller_state = controller_state
        self.commands = {}
        self.gamepad_state_needs_send = False

    async def _handle_gamepad_event(self, event):
        send_state = False
        if event.type == pygame.JOYAXISMOTION:
            if event.axis == 1: # y. 1: down
                self.controller_state.l_stick_state.set_v_float(event.value)
                send_state = True
                pass
            elif event.axis == 0: # x. 1: right
                self.controller_state.l_stick_state.set_h_float(event.value)
                send_state = True
                pass
            elif event.axis == 4: # right y. 1: down
                self.controller_state.r_stick_state.set_v_float(event.value)
                send_state = True
                pass
            elif event.axis == 3: # right x. 1: right
                self.controller_state.r_stick_state.set_h_float(event.value)
                send_state = True
                pass
            elif event.axis == 5: # r2- -1 unpressed -> 1 fully pressed
                pass
            elif event.axis == 2: # r2- -1 unpressed -> 1 fully pressed
                pass
        elif event.type == pygame.JOYBUTTONDOWN:
            if event.button in button_map:
                b = button_map[event.button]
                self.controller_state.button_state.set_button(b, True)
            send_state = True

        elif event.type == pygame.JOYBUTTONUP:
            if event.button in button_map:
                b = button_map[event.button]
                self.controller_state.button_state.set_button(b, False)
            send_state = True

        elif event.type == pygame.JOYHATMOTION:
            if event.value == (0, 0): # neutral
                self.controller_state.button_state.set_button('left', False)
                self.controller_state.button_state.set_button('right', False)
                self.controller_state.button_state.set_button('up', False)
                self.controller_state.button_state.set_button('down', False)
            elif event.value == (1, 0): # right
                self.controller_state.button_state.set_button('left', False)
                self.controller_state.button_state.set_button('right', True)
                self.controller_state.button_state.set_button('up', False)
                self.controller_state.button_state.set_button('down', False)
                pass
            elif event.value == (-1, 0): # left
                self.controller_state.button_state.set_button('left', True)
                self.controller_state.button_state.set_button('right', False)
                self.controller_state.button_state.set_button('up', False)
                self.controller_state.button_state.set_button('down', False)
                pass
            elif event.value == (0, 1): # up
                self.controller_state.button_state.set_button('left', False)
                self.controller_state.button_state.set_button('right', False)
                self.controller_state.button_state.set_button('up', True)
                self.controller_state.button_state.set_button('down', False)
                pass
            elif event.value == (0, -1): # down
                self.controller_state.button_state.set_button('left', False)
                self.controller_state.button_state.set_button('right', False)
                self.controller_state.button_state.set_button('up', False)
                self.controller_state.button_state.set_button('down', True)
                pass
            send_state = True

        if send_state:
            print(event)
            self.gamepad_state_needs_send = True
            #await self.controller_state.send()

    async def cmd_help(self):
        print('Button commands:')
        print(', '.join(self.controller_state.button_state.get_available_buttons()))
        print()
        print('Commands:')
        for name, fun in inspect.getmembers(self):
            if name.startswith('cmd_') and fun.__doc__:
                _print_doc(fun.__doc__)

        for name, fun in self.commands.items():
            if fun.__doc__:
                _print_doc(fun.__doc__)

        print('Commands can be chained using "&&"')
        print('Type "exit" to close.')

    @staticmethod
    def _set_stick(stick, direction, value):
        if direction == 'center':
            stick.set_center()
        elif direction == 'up':
            stick.set_up()
        elif direction == 'down':
            stick.set_down()
        elif direction == 'left':
            stick.set_left()
        elif direction == 'right':
            stick.set_right()
        elif direction in ('h', 'horizontal'):
            if value is None:
                raise ValueError(f'Missing value')
            try:
                val = int(value)
            except ValueError:
                raise ValueError(f'Unexpected stick value "{value}"')
            stick.set_h(val)
        elif direction in ('v', 'vertical'):
            if value is None:
                raise ValueError(f'Missing value')
            try:
                val = int(value)
            except ValueError:
                raise ValueError(f'Unexpected stick value "{value}"')
            stick.set_v(val)
        else:
            raise ValueError(f'Unexpected argument "{direction}"')

        return f'{stick.__class__.__name__} was set to ({stick.get_h()}, {stick.get_v()}).'

    async def cmd_stick(self, side, direction, value=None):
        """
        stick - Command to set stick positions.
        :param side: 'l', 'left' for left control stick; 'r', 'right' for right control stick
        :param direction: 'center', 'up', 'down', 'left', 'right';
                          'h', 'horizontal' or 'v', 'vertical' to set the value directly to the "value" argument
        :param value: horizontal or vertical value
        """
        if side in ('l', 'left'):
            stick = self.controller_state.l_stick_state
            return ControllerCLI._set_stick(stick, direction, value)
        elif side in ('r', 'right'):
            stick = self.controller_state.r_stick_state
            return ControllerCLI._set_stick(stick, direction, value)
        else:
            raise ValueError('Value of side must be "l", "left" or "r", "right"')

    async def _send_gamepad_state(self):
        while True:
            await asyncio.sleep(1 / 120)
            if self.gamepad_state_needs_send == True:
                print("sending state")
                self.gamepad_state_needs_send = False
                if self.controller_state != None:
                    await self.controller_state.send()

    async def _gamepad_poll(self, event_queue):
        print("begin gamepad polling")

        for i in range(0, pygame.joystick.get_count()):
            # create an Joystick object in our list
            joysticks.append(pygame.joystick.Joystick(i))
            # initialize them all (-1 means loop forever)
            joysticks[-1].init()
            # print a statement telling what the name of the controller is
            print ("Detected joystick "),joysticks[-1].get_name(),"'"
        while True:
            event = await event_queue.get()
            try:
                await self._handle_gamepad_event(event)
            except Exception as e:
                print()
                print("ERROR in gamepad handling")
                print(e)
                print()

    def add_command(self, name, command):
        if name in self.commands:
            raise ValueError(f'Command {name} already registered.')
        self.commands[name] = command

    async def run(self):
        loop = asyncio.get_event_loop()
        loop.set_debug(True)
        event_queue = asyncio.Queue()

        pygame_task = loop.run_in_executor(None, pygame_event_loop, loop, event_queue)
        gamepad_task = asyncio.ensure_future(self._gamepad_poll(event_queue))
        send_state_task = asyncio.ensure_future(self._send_gamepad_state())

        while True:
            user_input = await ainput(prompt='cmd >> ')
            if not user_input:
                continue

            buttons_to_push = []

            for command in user_input.split('&&'):
                cmd, *args = command.split()

                if cmd == 'exit':
                    return

                available_buttons = self.controller_state.button_state.get_available_buttons()

                if hasattr(self, f'cmd_{cmd}'):
                    try:
                        result = await getattr(self, f'cmd_{cmd}')(*args)
                        if result:
                            print(result)
                    except Exception as e:
                        print(e)
                elif cmd in self.commands:
                    try:
                        result = await self.commands[cmd](*args)
                        if result:
                            print(result)
                    except Exception as e:
                        print(e)
                elif cmd in available_buttons:
                    buttons_to_push.append(cmd)
                else:
                    print('command', cmd, 'not found, call help for help.')

            if buttons_to_push:
                await button_push(self.controller_state, *buttons_to_push)
            else:
                try:
                    await self.controller_state.send()
                except NotConnectedError:
                    logger.info('Connection was lost.')
                    return
        await gamepad_task
        await send_state_task
