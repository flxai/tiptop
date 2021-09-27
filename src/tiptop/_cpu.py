import cpuinfo
import psutil
from rich import box
from rich.panel import Panel
from rich.table import Table
from textual.widget import Widget

# TODO relative imports
from .braille_stream import BrailleStream


class CPU(Widget):
    def on_mount(self):
        # self.max_graph_width = 200

        num_cores = psutil.cpu_count(logical=False)
        num_threads = psutil.cpu_count(logical=True)

        self.cpu_total_stream = BrailleStream(50, 6, 0.0, 100.0)

        self.cpu_percent_streams = [
            BrailleStream(10, 1, 0.0, 100.0)
            for _ in range(num_threads)
            # BlockCharStream(10, 1, 0.0, 100.0) for _ in range(num_threads)
        ]

        temp_low = 20.0
        temp_high = psutil.sensors_temperatures()["coretemp"][0].high
        self.temp_total_stream = BrailleStream(50, 6, temp_low, temp_high, flipud=True)
        self.core_temp_streams = [
            BrailleStream(5, 1, temp_low, temp_high) for _ in range(num_cores)
        ]

        self.box_title = ", ".join(
            [
                f"{num_threads} threads",
                f"{num_cores} cores",
            ]
        )

        self.brand_raw = cpuinfo.get_cpu_info()["brand_raw"]
        self.collect_data()
        self.set_interval(2.0, self.collect_data)

    def collect_data(self):
        # CPU loads
        self.cpu_total_stream.add_value(psutil.cpu_percent())
        #
        load_indiv = psutil.cpu_percent(percpu=True)
        cpu_percent_colors = [val_to_color(val, 0.0, 100.0) for val in load_indiv]
        for stream, load in zip(self.cpu_percent_streams, load_indiv):
            stream.add_value(load)

        # CPU temperatures
        temps = psutil.sensors_temperatures()["coretemp"]
        self.temp_total_stream.add_value(temps[0].current)
        #
        for stream, temp in zip(self.core_temp_streams, temps[1:]):
            stream.add_value(temp.current)

        lines_cpu = self.cpu_total_stream.graph
        last_val_string = f"{self.cpu_total_stream.last_value:5.1f}%"
        lines0 = lines_cpu[0][: -len(last_val_string)] + last_val_string
        self.lines_cpu = [lines0] + lines_cpu[1:]
        #
        lines_temp = self.temp_total_stream.graph
        last_val_string = f"{round(self.temp_total_stream.last_value):3d}°C"
        lines0 = lines_temp[-1][: -len(last_val_string)] + last_val_string
        lines_temp = lines_temp[:-1] + [lines0]
        #
        cpu_total_graph = (
            "[color(4)]"
            + "\n".join(lines_cpu)
            + "[/]\n"
            + "[color(5)]"
            + "\n".join(lines_temp)
            + "[/]"
        )

        # threads 0 and 4 are in one core, display them next to each other, etc.
        cores = [0, 4, 1, 5, 2, 6, 3, 7]
        lines = [
            f"[{cpu_percent_colors[i]}]"
            + f"{self.cpu_percent_streams[i].graph[0]} "
            + f"{round(self.cpu_percent_streams[i].last_value):3d}%[/]"
            for i in cores
        ]
        # add temperature in every other line
        for k, stream in enumerate(self.core_temp_streams):
            lines[
                2 * k
            ] += f" [color(5)]{stream.graph[0]} {round(stream.last_value)}°C[/]"

        # load_avg = os.getloadavg()
        # subtitle = f"Load Avg:  {load_avg[0]:.2f}  {load_avg[1]:.2f}  {load_avg[2]:.2f}"
        subtitle = f"{round(psutil.cpu_freq().current):4d} MHz"

        # info_box_width = max(len(line) for line in lines) + 4
        info_box = Panel(
            "\n".join(lines),
            title=self.box_title,
            title_align="left",
            subtitle=subtitle,
            subtitle_align="left",
            border_style="color(7)",
            box=box.SQUARE,
            expand=False,
        )

        t = Table(expand=True, show_header=False, padding=0)
        t.add_column("graph", no_wrap=True, justify="right")
        t.add_column("box", no_wrap=True, justify="left")
        t.add_row(cpu_total_graph, info_box)

        self.panel = Panel(
            t,
            title=f"cpu - {self.brand_raw}",
            title_align="left",
            border_style="color(4)",
            box=box.SQUARE,
        )

        # textual method
        self.refresh()

    def render(self):
        return self.panel
