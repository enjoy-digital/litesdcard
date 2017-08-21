#!/usr/bin/env python3
from litex.build.xilinx import XC3SProg

prog = XC3SProg()
prog.load_bitstream("soc_sdsoc_papilio_pro/gateware/top.bit")
