#!/usr/bin/env python
# -*- coding: utf-8 -*-

import init_example
import os
import time
import numpy as np
import matplotlib.pyplot as plt

from koheron import connect
from ldk.drivers import Oscillo
from ldk.drivers import Laser

host = os.getenv('HOST','192.168.1.100')
client = connect(host, name='oscillo')

driver = Oscillo(client)
laser = Laser(client)

laser.start_laser()
laser.set_laser_current(0)
time.sleep(0.1)

current_max = 40
currents = np.linspace(0,current_max, num=100)

laser_powers = 0 * currents
measured_currents = 0 * currents

for i, current in enumerate(currents):
    laser.set_laser_current(current)
    time.sleep(0.02)
    laser_powers[i] = laser.get_laser_power()
    measured_currents[i] = laser.get_laser_current()
    print('laser power = ' + str(laser_powers[i]) + ' arb. units')

# Plot
fig1 = plt.figure('Power vs current')
plt.plot(currents, laser_powers)
plt.xlabel('Control current (mA)')
plt.ylabel('Laser power (arb. units)')

np.savetxt('power_vs_current.csv',
           np.transpose([currents, laser_powers]),
           delimiter=',',
           fmt='%1.4e')

laser.stop_laser()
plt.show()
