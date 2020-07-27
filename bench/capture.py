#!/usr/bin/env python3

# This file is Copyright (c) 2020 Florent Kermarrec <florent@enjoy-digital.fr>
# License: BSD


import argparse
import socket

from litex import RemoteClient

parser = argparse.ArgumentParser()
parser.add_argument("--value",        default="0",   help="Trigger Value.")
parser.add_argument("--mask",         default="0",   help="Trigger Mask.")
parser.add_argument("--count",        default="1e6", help="Sample Count.")
parser.add_argument("--downsampling", default="1",   help="Sample Downsampling.")
args = parser.parse_args()

wb = RemoteClient()
wb.open()

# # #

def num(s):
    try:
        return int(s, 0)
    except ValueError:
        return int(float(s))

class Sampler:
    def run(self, trig_value=0, trig_mask=0, sample_count=int(1e6), sample_downsampling=1):
        # Disable Sampler
        wb.regs.sampler_enable.write(0)

        # Configure trigger
        wb.regs.sampler_trig_value.write(trig_value)
        wb.regs.sampler_trig_mask.write(trig_mask)

        # Configure count/downsampling
        wb.regs.sampler_sample_count.write(sample_count)
        wb.regs.sampler_sample_downsampling.write(sample_downsampling)

        # Enable Sampler
        wb.regs.sampler_enable.write(1)

        # Capture
        data_count = 0
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("192.168.1.100", 2000))
        f = open("capture.bin", "wb")
        while data_count < sample_count:
            data, addr = sock.recvfrom(1024)

            f.write(data)
            data_count += len(data)

sampler = Sampler()
sampler.run(
	trig_value          = num(args.value),
	trig_mask           = num(args.mask),
	sample_count        = num(args.count),
	sample_downsampling = num(args.downsampling)
)

# # #

wb.close()
