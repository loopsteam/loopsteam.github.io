import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from fontTools.ttLib import TTFont
import threading
import queue
import multiprocessing
from pathlib import Path
import concurrent.futures
from functools import partial

def convert_single_font(args):
    input_path, output_format, compression_level = args
    try:
        output_path = os.path.splitext(input_path)[0] + f'.{output_format}'
        
        # 优化1：使用上下文管理器自动关闭文件
        with TTFont(input_path, lazy=True, recalcBBoxes=False, recalcTimestamp=False) as font:
            font.flavor = output_format
            
            # 优化2：根据不同格式使用最优压缩设置
            if output_format == 'woff2':
                font.save(output_path, compression="woff2")
            elif output_format == 'woff':
                font.save(output_path, compress=True)
            else:
                font.save(output_path)
                
        return True, output_path
    except Exception as e:
        return False, str(e)

class TTFConverterApp:
    def __init__(self, master):
        self.master = master
        master.title("TTF 转换工具 v2.0")
        # 优化3：使用最优进程数
        self.cpu_count = min(multiprocessing.cpu_count(), 8)  # 限制最大进程数
        self.queue = queue.Queue()
        self.files_to_convert = []
        self.chunk_size = 5  # 优化4：添加批处理大小
        self.create_widgets()
        self.master.after(100, self.process_queue)

    def create_widgets(self):
        # 文件选择部分
        self.file_label = ttk.Label(self.master, text="选择 TTF 文件:")
        self.file_label.grid(row=0, column=0, padx=5, pady=5, sticky="w")

        self.file_entry = ttk.Entry(self.master, width=40)
        self.file_entry.grid(row=0, column=1, padx=5, pady=5)

        self.browse_button = ttk.Button(self.master, text="浏览...", command=self.browse_file)
        self.browse_button.grid(row=0, column=2, padx=5, pady=5)

        # 格式选择
        self.format_label = ttk.Label(self.master, text="输出格式:")
        self.format_label.grid(row=1, column=0, padx=5, pady=5, sticky="w")

        self.format_var = tk.StringVar()
        self.format_combobox = ttk.Combobox(self.master,
                                            textvariable=self.format_var,
                                            values=('woff2', 'woff'),
                                            state='readonly')
        self.format_combobox.current(0)
        self.format_combobox.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        # 修改进度条和状态标签的布局
        self.progress_frame = ttk.Frame(self.master)
        self.progress_frame.grid(row=2, column=0, columnspan=3, padx=5, pady=10)

        self.progress = ttk.Progressbar(self.progress_frame, orient="horizontal",
                                        length=200, mode="determinate")
        self.progress.pack(side=tk.LEFT, padx=(0, 5))

        self.progress_label = ttk.Label(self.progress_frame, text="0%")
        self.progress_label.pack(side=tk.LEFT)

        # 转换按钮
        self.convert_button = ttk.Button(self.master,
                                         text="开始转换",
                                         command=self.start_conversion)
        self.convert_button.grid(row=3, column=1, padx=5, pady=5)

        # 新增状态标签
        self.status_label = ttk.Label(self.master, text="准备就绪", foreground="#666")
        self.status_label.grid(row=4, column=0, columnspan=3, sticky="ew", padx=5, pady=5)

    def browse_file(self):
        file_path = filedialog.askopenfilename(
            title="选择 TTF 文件",
            filetypes=(("TTF 字体文件", "*.ttf"),)
        )
        if file_path:
            self.file_entry.delete(0, tk.END)
            self.file_entry.insert(0, file_path)

    def start_conversion(self):
        if not self.files_to_convert:
            messagebox.showerror("错误", "请先选择要转换的文件")
            return

        self.convert_button.config(state="disabled")
        output_format = self.format_var.get()
        compression_level = self.compression_var.get()
        num_processes = self.process_var.get()

        # 优化5：使用线程池执行进程池操作
        def conversion_thread():
            try:
                # 优化6：根据文件大小动态调整进程数
                total_size = sum(os.path.getsize(f) for f in self.files_to_convert)
                if total_size < 1024 * 1024 * 10:  # 小于10MB
                    num_processes = min(2, len(self.files_to_convert))
                
                with multiprocessing.Pool(processes=num_processes) as pool:
                    total_files = len(self.files_to_convert)
                    completed_files = 0

                    # 优化7：批量处理参数
                    conversion_args = [(f, output_format, compression_level) 
                                     for f in self.files_to_convert]
                    
                    # 优化8：使用imap处理大量文件
                    for result in pool.imap_unordered(convert_single_font, 
                                                    conversion_args,
                                                    chunksize=self.chunk_size):
                        completed_files += 1
                        success, message = result
                        
                        progress = (completed_files / total_files) * 100
                        self.queue.put(("progress", (
                            progress,
                            f"正在转换... ({completed_files}/{total_files})",
                            f"{int(progress)}%"
                        )))

                self.queue.put(("success", f"已完成 {completed_files} 个文件的转换"))
            except Exception as e:
                self.queue.put(("error", str(e)))

        # 优化9：使用线程执行转换
        threading.Thread(target=conversion_thread, daemon=True).start()

    def browse_directory(self):
        directory = filedialog.askdirectory(title="选择包含字体文件的文件夹")
        if directory:
            self.files_to_convert = []
            # 优化10：使用生成器减少内存使用
            path = Path(directory)
            for ext in ['.ttf', '.otf']:
                self.files_to_convert.extend(
                    str(p) for p in path.rglob(f'*{ext}')
                    if p.is_file() and p.stat().st_size > 0
                )
            self.update_files_list()

    def process_queue(self):
        try:
            while True:
                msg_type, data = self.queue.get_nowait()
                if msg_type == "progress":
                    value, message, percentage = data
                    self.progress['value'] = value
                    if message:
                        self.status_label.config(text=message)
                    if percentage:
                        self.progress_label.config(text=percentage)
                elif msg_type == "success":
                    messagebox.showinfo("成功", data)
                    self.reset_ui()
                elif msg_type == "error":
                    messagebox.showerror("错误", data)
                    self.reset_ui()
        except queue.Empty:
            pass
        self.master.after(100, self.process_queue)

    def reset_ui(self):
        self.progress['value'] = 0
        self.progress_label.config(text="0%")
        self.status_label.config(text="准备就绪")
        self.convert_button.config(state="enabled")


if __name__ == "__main__":
    root = tk.Tk()
    app = TTFConverterApp(root)
    root.mainloop()


