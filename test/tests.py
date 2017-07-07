from litex.gen import *
from litex.soc.interconnect import stream

from sdphy import *

class TopTest(Module):
    def __init__(self, platform):
        self.submodules.phy = SDPHY(platform.request('sdcard'))
        self.submodules.test = SDTest()

        self.comb += [
            self.test.source.connect(self.phy.csink),
            self.phy.csource.ready.eq(1),
        ]

class SDTest(Module):
    def __init__(self):
        self.source = stream.Endpoint([('data', 8), ('rdwr', 1)])

        cmd0 = [
            (SDCARD_CTRL_WRITE, 0x40 | 0, 0),
            (SDCARD_CTRL_WRITE, 0x00, 0),
            (SDCARD_CTRL_WRITE, 0x00, 0),
            (SDCARD_CTRL_WRITE, 0x00, 0),
            (SDCARD_CTRL_WRITE, 0x00, 0),
            (SDCARD_CTRL_WRITE, 0x95, 1),
        ]

        cmd8 = [
            (SDCARD_CTRL_WRITE, 0x40 | 8, 0),
            (SDCARD_CTRL_WRITE, 0x00, 0),
            (SDCARD_CTRL_WRITE, 0x00, 0),
            (SDCARD_CTRL_WRITE, 0x01, 0),
            (SDCARD_CTRL_WRITE, 0xaa, 0),
            (SDCARD_CTRL_WRITE, 0x87, 0),
            (SDCARD_CTRL_READ,  5,    1),
        ]

        cmd55 = [
            (SDCARD_CTRL_WRITE, 0x40 | 55, 0),
            (SDCARD_CTRL_WRITE, 0x00, 0),
            (SDCARD_CTRL_WRITE, 0x00, 0),
            (SDCARD_CTRL_WRITE, 0x00, 0),
            (SDCARD_CTRL_WRITE, 0x00, 0),
            (SDCARD_CTRL_WRITE, 0x65, 0),
            (SDCARD_CTRL_READ,  5,    1),
        ]

        acmd41 = [
            (SDCARD_CTRL_WRITE, 0x40 | 41, 0),
            (SDCARD_CTRL_WRITE, 0x00, 0),
            (SDCARD_CTRL_WRITE, 0x10, 0),
            (SDCARD_CTRL_WRITE, 0x00, 0),
            (SDCARD_CTRL_WRITE, 0x00, 0),
            (SDCARD_CTRL_WRITE, 0x5f, 0),
            (SDCARD_CTRL_READ,  5,    1),
        ]

        mylist = cmd0 + cmd8 + cmd55 + acmd41

        sel = Signal(max=len(mylist))

        mycases = {}
        for i, (rdwr, data, last) in enumerate(mylist):
            mycases[i] = [
                self.source.rdwr.eq(rdwr),
                self.source.data.eq(data),
                self.source.last.eq(last),
                self.source.valid.eq(1),
            ]

        counter = Signal(32)

        fsm = FSM()
        self.submodules.fsm = fsm

        fsm.act("IDLE",
            NextValue(sel, 0),
            NextValue(counter, counter + 1),
            If(counter > 3200,
                NextValue(counter, 0),
                NextState("SEND"),
            )
        )
        fsm.act("SEND",
            Case(sel, mycases),
            If(self.source.ready,
                NextValue(sel, sel + 1),
                If(sel == len(mylist)-1,
                    NextState("IDLE"),
                ),
            ),
        )
        fsm.act("STOP",
            NextValue(sel, 0),
        )

class DataGen(Module):
    def __init__(self):
        self.source = stream.Endpoint([('data', 8)])

        initcnt = Signal(32)
        counter = Signal(32)

        self.comb += [
            If(initcnt >= 50000000,
                self.source.data.eq(counter),
                self.source.valid.eq(counter < 512),
                self.source.last.eq(counter == 512-1),
            ),
        ]

        self.sync += [
            If(initcnt < 50000000,
                initcnt.eq(initcnt + 1),
            ).Else(
                If(self.source.valid & self.source.ready,
                    If(counter < 512,
                        counter.eq(counter + 1),
                    ),
                ),
            ),
        ]

def main():
    import papilio_pro
    platform = papilio_pro.Platform()
    top = TopTest(platform)
    platform.build(top)

if __name__ == "__main__":
    main()
