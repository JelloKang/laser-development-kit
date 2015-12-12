#!/usr/bin/env python
# -*- coding: utf-8 -*-

import time
import numpy as np
from lase import Lase

class Oscillo():
    """ Driver for the oscillo bitstream
    """
    
    def __init__(self, client, map_size=4096, 
                 verbose = False, current_mode = 'pwm'):
        n = 8192
        self.lase_base = Lase(n, client, map_size = 4096, current_mode = 'pwm')

        # Addresses of memory maps
        _adc_1_addr = int('0x42000000',0)
        _adc_2_addr = int('0x44000000',0)
        
        # Config offsets
        self._avg_off = 24   

        # Add memory maps
        self._adc_1 = self.lase_base.dvm.add_memory_map(_adc_1_addr, self.lase_base.n/1024*map_size)
        self._adc_2 = self.lase_base.dvm.add_memory_map(_adc_2_addr, self.lase_base.n/1024*map_size)
       
        self.avg_on = False

        self.adc = np.zeros((2,self.lase_base.n))
        self.spectrum = np.zeros((2,self.lase_base.n/2))
        self.avg_spectrum = np.zeros((2,self.lase_base.n/2))
        self.ideal_amplitude_waveform = np.zeros(self.lase_base.n)
        self.amplitude_transfer_function = np.ones(self.lase_base.sampling.n, dtype=np.dtype('complex64'))

        # Correction
        sigma_freq = 5e6 # Hz
        self.gaussian_filter = 1.0 * np.exp(-1.0*self.lase_base.sampling.f_fft**2/(2*sigma_freq**2))
        
        # Calibration
        self.adc_offset = np.zeros(2)
        self.optical_power = np.ones(2)
        self.power = np.ones(2)
        
        self.reset()
    
    def reset(self):
        self.lase_base.reset()
        self.avg_on = False
        self.set_averaging(self.avg_on)
        
    def set_averaging(self, avg_on, reset=True):
        self.avg_on = avg_on
        if self.avg_on:
            self.lase_base.dvm.clear_bit(self.lase_base._config, self.lase_base._avg1_off,0)
            self.lase_base.dvm.clear_bit(self.lase_base._config, self.lase_base._avg2_off,0)
        else:
            self.lase_base.dvm.set_bit(self.lase_base._config, self.lase_base._avg1_off,0)
            self.lase_base.dvm.set_bit(self.lase_base._config, self.lase_base._avg2_off,0)

    def get_adc(self):
        self.lase_base.dvm.set_bit(self.lase_base._config, self.lase_base._addr_off,1) 
        time.sleep(0.001)
        self.adc[0,:] = self.lase_base.dvm.read_buffer(self._adc_1, 0, self.lase_base.n)
        self.adc[1,:] = self.lase_base.dvm.read_buffer(self._adc_2, 0, self.lase_base.n)
        
        # Check reception
        if np.isnan(self.adc[0,0]) or np.isnan(self.adc[1,0]):
            self._is_failed = True
            return
        
        self.adc = np.mod(self.adc-2**31,2**32)-2**31
        
        if self.avg_on:
            n_avg1 = self.lase_base.dvm.read(self.lase_base._status,self.lase_base._n_avg1_off)
            # n_avg2 = self.dvm.read(self._status,self._n_avg2_off) # unused
            self.adc /= np.float(n_avg1)
            
        self.lase_base.dvm.clear_bit(self.lase_base._config, self.lase_base._addr_off,1)
        self.adc[0,:] -= self.adc_offset[0]
        self.adc[1,:] -= self.adc_offset[1]
        self.adc[0,:] *= self.optical_power[0] /self.power[0]
        self.adc[1,:] *= self.optical_power[1] /self.power[1]
        
    def _white_noise(self, n_freqs, n_stop=None):
        if n_stop == None:
            n_stop=n_freqs
        amplitudes = np.zeros(n_freqs)
        amplitudes[0:n_stop] = 1
        random_phases = 2 * np.pi * np.random.rand(n_freqs)        
        white_noise = np.fft.irfft(amplitudes * np.exp(1j * random_phases))
        white_noise = np.fft.fft(white_noise)
        white_noise[0] = 0.01
        white_noise[self.sampling.n/2]=1    
        white_noise = np.real(np.fft.ifft(white_noise))
        white_noise /= 1.7 * np.max(np.abs(white_noise))        
        return white_noise

    def get_amplitude_transfer_function(self, channel_dac=0, 
                                        channel_adc =0, transfer_avg=100):
        n_freqs = self.sampling.n/2 +1
        self.amplitude_transfer_function *= 0
        
        for i in range(transfer_avg):
            white_noise = self._white_noise(n_freqs)
            self.dac[channel_dac,:] = white_noise
            self.set_dac()
            time.sleep(0.01)
            self.get_adc()
            self.amplitude_transfer_function += np.fft.fft(self.adc[channel_adc,:])/np.fft.fft(white_noise)
        self.amplitude_transfer_function = self.amplitude_transfer_function/transfer_avg
        self.amplitude_transfer_function[0] = 1
        self.dac[channel_dac,:] = np.zeros(self.sampling.n)
        self.set_dac()

    def get_correction(self):
        tmp = np.fft.fft(self.amplitude_error)/self.amplitude_transfer_function
        tmp[0] = 0
        tmp = self.gaussian_filter * tmp
        return np.real(np.fft.ifft(tmp))

    def optimize_amplitude(self, alpha=1, channel=0):
        self.amplitude_error = (self.adc[0,:] - np.mean(self.adc[0,:])) - self.ideal_amplitude_waveform
        self.dac[channel,:] -= alpha*self.get_correction()
        
    def get_spectrum(self):
        fft_adc = np.fft.fft(self.adc, axis=1)
        self.spectrum = fft_adc[:,0:self.sampling.n/2]
        
    def get_avg_spectrum(self, n_avg=1):
        self.avg_spectrum = np.zeros((2,self.sampling.n/2))               
        for i in range(n_avg):
            self.get_adc()
            fft_adc = np.abs(np.fft.fft(self.adc, axis=1))
            self.avg_spectrum += fft_adc[:,0:self.sampling.n/2]                    

        self.avg_spectrum = self.avg_spectrum / n_avg
        
    def set_amplitude_transfer_function(self, amplitude_transfer_function):
        self.amplitude_transfer_function = amplitude_transfer_function
