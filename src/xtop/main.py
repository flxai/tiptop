import socket
import time
from datetime import datetime, timedelta
from math import ceil
from typing import NamedTuple

import psutil
from rich import align, box
from rich.columns import Columns
from rich.panel import Panel
from rich.table import Table
from textual.app import App
from textual.message_pump import CallbackError
from textual.widget import Widget

num_to_braille = {
    (0, 0): " ",
    (0, 1): "⢀",
    (0, 2): "⢠",
    (0, 3): "⢰",
    (0, 4): "⢸",
    #
    (1, 0): "⡀",
    (1, 1): "⣀",
    (1, 2): "⣠",
    (1, 3): "⣰",
    (1, 4): "⣸",
    #
    (2, 0): "⡄",
    (2, 1): "⣄",
    (2, 2): "⣤",
    (2, 3): "⣴",
    (2, 4): "⣼",
    #
    (3, 0): "⡆",
    (3, 1): "⣆",
    (3, 2): "⣦",
    (3, 3): "⣶",
    (3, 4): "⣾",
    #
    (4, 0): "⡇",
    (4, 1): "⣇",
    (4, 2): "⣧",
    (4, 3): "⣷",
    (4, 4): "⣿",
}


class BrailleStream:
    def __init__(self, num_chars: int, minval: float, maxval: float):
        self._graphs = [" " * num_chars, " " * num_chars]
        self.minval = minval
        self.maxval = maxval
        self._last_k = 0
        self.last_value: float = minval

    def add_value(self, value):
        k = ceil((value - self.minval) / (self.maxval - self.minval) * 4)
        char = num_to_braille[(self._last_k, k)]

        # roll list
        self._graphs.append(self._graphs.pop(0))
        # update stream
        self._graphs[0] = self._graphs[0][1:] + char

        self.last_value = value
        self._last_k = k

    @property
    def graph(self):
        return self._graphs[0]


def argsort(seq):
    return sorted(range(len(seq)), key=seq.__getitem__)


# https://stackoverflow.com/a/1094933/353337
def sizeof_fmt(num):
    assert num >= 0
    for unit in ["B", "k", "M", "G", "T", "P", "E", "Z"]:
        # actuall 1024, but be economical with the return string size:
        if num < 1000:
            return f"{round(num):3d}{unit}"
        num /= 1024
    return f"{round(num):3d}Y"


def val_to_color(val: float, minval: float, maxval: float) -> str:
    t = (val - minval) / (maxval - minval)
    k = round(t * 3)
    return {0: "color(4)", 1: "color(6)", 2: "color(6)", 3: "color(2)"}[k]


class InfoLine(Widget):
    def render(self):
        now = datetime.now().strftime("%c")
        uptime_s = time.time() - psutil.boot_time()
        d = datetime(1, 1, 1) + timedelta(seconds=uptime_s)

        battery = psutil.sensors_battery().percent
        return align.Align(
            "[color(8)]"
            + f"{now}, "
            + f"up {d.day - 1} days, {d.hour}:{d.minute}, "
            + f"BAT {round(battery)}%"
            + "[/]",
            "center",
        )

    def on_mount(self):
        self.set_interval(2.0, self.refresh)


class CPU(Widget):
    def on_mount(self):
        self.data = []
        self.num_cores = psutil.cpu_count(logical=False)
        self.num_threads = psutil.cpu_count(logical=True)

        self.cpu_percent_streams = [
            BrailleStream(10, 0.0, 100.0) for _ in range(self.num_threads)
        ]

        temp_low = 30.0
        temp_high = psutil.sensors_temperatures()["coretemp"][0].high
        self.core_temp_streams = [
            BrailleStream(10, temp_low, temp_high) for _ in range(self.num_cores)
        ]

        self.collect_data()
        self.set_interval(2.0, self.collect_data)

        self.box_title = ", ".join(
            [
                f"{self.num_cores} cores",
                f"{self.num_threads} threads",
            ]
        )

    def collect_data(self):
        # self.temp_total.pop(0)
        # self.temp_total.append(psutil.sensors_temperatures()["coretemp"][0].current)

        for stream, temp in zip(
            self.core_temp_streams, psutil.sensors_temperatures()["coretemp"][1:]
        ):
            stream.add_value(temp.current)

        # self.cpu_percent_data.pop(0)
        # self.cpu_percent_data.append(psutil.cpu_percent())
        # self.color_total = val_to_color(self.cpu_percent_data[-1], 0.0, 100.0)

        load_indiv = psutil.cpu_percent(percpu=True)
        self.cpu_percent_colors = [val_to_color(val, 0.0, 100.0) for val in load_indiv]
        for stream, load in zip(self.cpu_percent_streams, load_indiv):
            stream.add_value(load)

        # textual method
        self.refresh()

    def render(self):
        # percent = round(self.cpu_percent_data[-1])
        # lines += [
        #     f"[b]CPU[/] [{self.color_total}]{self.cpu_percent_graph} {percent:3d}%[/]  "
        #     f"[color(5)]{self.total_temp_graph} {int(self.temp_total[-1])}°C[/]"
        # ]

        # threads 0 and 4 are in one core, display them next to each other, etc.
        cores = [0, 4, 1, 5, 2, 6, 3, 7]
        lines = [
            f"[{self.cpu_percent_colors[i]}]"
            + f"{self.cpu_percent_streams[i].graph} "
            + f"{round(self.cpu_percent_streams[i].last_value):3d}%[/]"
            for i in cores
        ]
        # add temperature in every other line
        for k, stream in enumerate(self.core_temp_streams):
            lines[2 * k] += f" [color(5)]{stream.graph} {round(stream.last_value)}°C[/]"

        # load_avg = os.getloadavg()
        # subtitle = f"Load Avg:  {load_avg[0]:.2f}  {load_avg[1]:.2f}  {load_avg[2]:.2f}"
        subtitle = f"{round(psutil.cpu_freq().current):4d} MHz"

        info_box = align.Align(
            Panel(
                "\n".join(lines),
                title=self.box_title,
                title_align="left",
                subtitle=subtitle,
                subtitle_align="left",
                border_style="color(8)",
                box=box.SQUARE,
            ),
            "right",
            vertical="middle",
        )

        t = Table.grid(expand=True)
        t.add_column("full", no_wrap=True)
        t.add_column("box", no_wrap=True)
        # t.add_row(", ".join(["dasdas\n"] * 100), info_box)
        t.add_row("ghtryhFESAD", info_box)
        # c = Columns(["dasdas", info_box], expand=True)

        return Panel(
            t, title=f"cpu", title_align="left", border_style="color(4)", box=box.SQUARE
        )


class Mem(Widget):
    def render(self) -> Panel:
        return Panel(
            "",
            title="mem",
            title_align="left",
            border_style="color(2)",
            box=box.SQUARE,
        )


class ProcInfo(NamedTuple):
    pid: int
    name: str
    cmdline: str
    cpu_percent: float
    num_threads: int
    username: str
    memory: int


class ProcsList(Widget):
    def on_mount(self):
        self.collect_data()
        self.set_interval(6.0, self.collect_data)

    def collect_data(self):
        processes = list(psutil.process_iter())
        cpu_percent = [p.cpu_percent() for p in processes]
        # sort by cpu_percent
        idx = argsort(cpu_percent)[::-1]

        # Pick top 20 and cache all values. The process might not be there anymore if we
        # try to retrieve the details at a later time.
        self.processes = []
        for k in idx[:30]:
            p = processes[k]
            with p.oneshot():
                try:
                    self.processes.append(
                        ProcInfo(
                            p.pid,
                            p.name(),
                            p.cmdline(),
                            cpu_percent[k],
                            p.num_threads(),
                            p.username(),
                            p.memory_info().rss,
                        )
                    )
                except CallbackError:
                    pass

        self.refresh()

    def render(self) -> Panel:
        table = Table(show_header=True, header_style="bold", box=None)
        table.add_column("pid", min_width=6, no_wrap=True)
        table.add_column("program", max_width=10, style="color(2)", no_wrap=True)
        table.add_column("args", max_width=20, no_wrap=True)
        table.add_column("#th", width=3, style="color(2)", no_wrap=True)
        table.add_column("user", no_wrap=True)
        table.add_column("memB", style="color(2)", no_wrap=True)
        table.add_column("[u]cpu%[/]", width=5, style="color(2)", no_wrap=True)

        table.padding = 0
        table.border_style = "none"
        for p in self.processes:
            table.add_row(
                f"{p.pid:6d}",
                p.name,
                " ".join(p.cmdline[1:]),
                f"{p.num_threads:3d}",
                p.username,
                sizeof_fmt(p.memory),
                f"{p.cpu_percent:5.1f}",
            )

        return Panel(
            table,
            title="proc",
            title_align="left",
            border_style="color(6)",
            box=box.SQUARE,
        )


class Net(Widget):
    def render(self) -> Panel:
        ip = socket.gethostbyname(socket.gethostname())
        return Panel(
            "",
            title=f"net - {ip}",
            title_align="left",
            border_style="color(1)",
            box=box.SQUARE,
        )


class Xtop(App):
    async def on_mount(self) -> None:
        await self.view.dock(InfoLine(), edge="top", size=1, name="info")
        await self.view.dock(CPU(), edge="top", size=14, name="cpu")
        await self.view.dock(ProcsList(), edge="right", size=70, name="proc")
        await self.view.dock(Mem(), edge="top", size=20, name="mem")
        await self.view.dock(Net(), edge="bottom", name="net")

    async def on_load(self, _):
        await self.bind("i", "view.toggle('info')", "Toggle info")
        await self.bind("c", "view.toggle('cpu')", "Toggle cpu")
        await self.bind("m", "view.toggle('mem')", "Toggle mem")
        await self.bind("n", "view.toggle('net')", "Toggle net")
        await self.bind("p", "view.toggle('proc')", "Toggle proc")
        await self.bind("q", "quit", "quit")


Xtop.run()
