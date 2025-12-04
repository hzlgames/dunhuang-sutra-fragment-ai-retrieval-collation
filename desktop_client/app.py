"""
敦煌残卷分析桌面客户端主程序
基于 PySide6 实现的 GUI 应用
"""
import os
import sys
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QFileDialog,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
    QProgressBar,
    QGroupBox,
    QCheckBox,
    QSpinBox,
    QLineEdit,
    QTabWidget,
    QTextEdit,
    QSplitter,
    QStatusBar,
)
from PySide6.QtCore import Qt, QTimer, Signal, QObject, QThread
from PySide6.QtGui import QColor, QFont

from .config import config
from .models import TaskRecord, TaskStatus, TaskType
from .task_store import task_store
from .api_client import api_client, APIError


# ------------------------------------------------------------------ #
# 工作线程信号
# ------------------------------------------------------------------ #

class WorkerSignals(QObject):
    """工作线程信号"""
    task_updated = Signal(str)  # local_id
    upload_finished = Signal(str, bool, str)  # local_id, success, message
    error = Signal(str)  # error message


# ------------------------------------------------------------------ #
# 上传工作线程
# ------------------------------------------------------------------ #

class UploadWorker(QThread):
    """单个上传任务的工作线程"""
    
    def __init__(self, task: TaskRecord, signals: WorkerSignals):
        super().__init__()
        self.task = task
        self.signals = signals
    
    def run(self):
        try:
            # 更新状态为上传中
            task_store.update_task(self.task.local_id, status=TaskStatus.UPLOADING)
            self.signals.task_updated.emit(self.task.local_id)
            
            if self.task.task_type == TaskType.SINGLE:
                # 单图上传
                image_path = Path(self.task.image_paths[0])
                
                # 检查是否是断点续传
                if self.task.session_id:
                    task_id, session_id = api_client.resume_job(
                        self.task.session_id, image_path
                    )
                else:
                    task_id = api_client.upload_single_image(image_path)
                    session_id = None
                
                task_store.update_task(
                    self.task.local_id,
                    task_id=task_id,
                    session_id=session_id,
                    status=TaskStatus.PENDING,
                )
            else:
                # 批量上传
                image_paths = [Path(p) for p in self.task.image_paths]
                batch_id = api_client.upload_batch(image_paths)
                task_store.update_task(
                    self.task.local_id,
                    batch_id=batch_id,
                    status=TaskStatus.BATCH_PENDING,
                    total_jobs=len(image_paths),
                )
            
            self.signals.upload_finished.emit(self.task.local_id, True, "上传成功")
        except APIError as e:
            task_store.update_task(
                self.task.local_id,
                status=TaskStatus.FAILED,
                error=str(e),
            )
            self.signals.upload_finished.emit(self.task.local_id, False, str(e))
        except Exception as e:
            task_store.update_task(
                self.task.local_id,
                status=TaskStatus.FAILED,
                error=str(e),
            )
            self.signals.upload_finished.emit(self.task.local_id, False, str(e))


# ------------------------------------------------------------------ #
# 主窗口
# ------------------------------------------------------------------ #

class MainWindow(QMainWindow):
    """主窗口"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("敦煌残卷 AI 分析工具")
        self.setMinimumSize(900, 600)
        
        # 工作线程管理
        self.worker_signals = WorkerSignals()
        self.worker_signals.task_updated.connect(self._on_task_updated)
        self.worker_signals.upload_finished.connect(self._on_upload_finished)
        self.worker_signals.error.connect(self._on_error)
        
        self.upload_workers: List[UploadWorker] = []
        self.upload_queue: List[str] = []  # 等待上传的 local_id 列表
        
        # 轮询定时器
        self.poll_timer = QTimer()
        self.poll_timer.timeout.connect(self._poll_tasks)
        
        # 服务器信息
        self.output_dir: Optional[str] = None
        self.supports_batch = False
        
        # 初始化 UI
        self._init_ui()
        self._load_tasks()
        
        # 检查服务器连接
        QTimer.singleShot(500, self._check_server)
    
    def _init_ui(self):
        """初始化界面"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        
        # 顶部信息栏
        top_bar = self._create_top_bar()
        main_layout.addWidget(top_bar)
        
        # 主内容区
        splitter = QSplitter(Qt.Vertical)
        
        # 上半部分：控制面板 + 任务列表
        upper_widget = QWidget()
        upper_layout = QVBoxLayout(upper_widget)
        upper_layout.setContentsMargins(0, 0, 0, 0)
        
        # 控制面板
        control_panel = self._create_control_panel()
        upper_layout.addWidget(control_panel)
        
        # 任务列表
        task_group = QGroupBox("任务列表")
        task_layout = QVBoxLayout(task_group)
        self.task_table = self._create_task_table()
        task_layout.addWidget(self.task_table)
        
        # 任务操作按钮
        task_buttons = QHBoxLayout()
        self.btn_cancel = QPushButton("取消选中")
        self.btn_cancel.clicked.connect(self._cancel_selected)
        self.btn_retry = QPushButton("重试选中")
        self.btn_retry.clicked.connect(self._retry_selected)
        self.btn_view_result = QPushButton("查看结果")
        self.btn_view_result.clicked.connect(self._view_selected_result)
        self.btn_clear_completed = QPushButton("清除已完成")
        self.btn_clear_completed.clicked.connect(self._clear_completed)
        
        task_buttons.addWidget(self.btn_cancel)
        task_buttons.addWidget(self.btn_retry)
        task_buttons.addWidget(self.btn_view_result)
        task_buttons.addStretch()
        task_buttons.addWidget(self.btn_clear_completed)
        task_layout.addLayout(task_buttons)
        
        upper_layout.addWidget(task_group)
        splitter.addWidget(upper_widget)
        
        # 下半部分：详情/日志
        self.detail_tabs = QTabWidget()
        
        # 结果详情
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setFont(QFont("Consolas", 10))
        self.detail_tabs.addTab(self.result_text, "结果详情")
        
        # AI 处理过程
        self.process_text = QTextEdit()
        self.process_text.setReadOnly(True)
        self.process_text.setFont(QFont("Consolas", 10))
        self.detail_tabs.addTab(self.process_text, "AI 处理过程")
        
        splitter.addWidget(self.detail_tabs)
        splitter.setSizes([400, 200])
        
        main_layout.addWidget(splitter)
        
        # 状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪")
    
    def _create_top_bar(self) -> QWidget:
        """创建顶部信息栏"""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # 服务器状态
        self.server_status_label = QLabel("服务器: 检查中...")
        layout.addWidget(self.server_status_label)
        
        layout.addStretch()
        
        # 输出目录
        self.output_dir_label = QLabel("输出目录: -")
        layout.addWidget(self.output_dir_label)
        
        self.btn_change_output = QPushButton("更改目录")
        self.btn_change_output.clicked.connect(self._change_output_dir)
        self.btn_change_output.setToolTip("选择结果文件的保存目录")
        layout.addWidget(self.btn_change_output)
        
        self.btn_open_output = QPushButton("打开目录")
        self.btn_open_output.clicked.connect(self._open_output_dir)
        self.btn_open_output.setEnabled(False)
        layout.addWidget(self.btn_open_output)
        
        return widget
    
    def _create_control_panel(self) -> QWidget:
        """创建控制面板"""
        group = QGroupBox("添加任务")
        layout = QHBoxLayout(group)
        
        # 选择图片按钮
        self.btn_select_images = QPushButton("选择图片")
        self.btn_select_images.clicked.connect(self._select_images)
        layout.addWidget(self.btn_select_images)
        
        # 批处理模式复选框
        self.chk_batch_mode = QCheckBox("批处理模式")
        self.chk_batch_mode.setToolTip("勾选后，多张图片将作为一个批处理任务提交")
        layout.addWidget(self.chk_batch_mode)
        
        layout.addStretch()
        
        # 并发数设置
        layout.addWidget(QLabel("并发上传数:"))
        self.spin_concurrent = QSpinBox()
        self.spin_concurrent.setRange(1, 10)
        self.spin_concurrent.setValue(config.max_concurrent_uploads)
        self.spin_concurrent.valueChanged.connect(self._on_concurrent_changed)
        layout.addWidget(self.spin_concurrent)
        
        # 刷新按钮
        self.btn_refresh = QPushButton("刷新状态")
        self.btn_refresh.clicked.connect(self._refresh_all)
        layout.addWidget(self.btn_refresh)
        
        return group
    
    def _create_task_table(self) -> QTableWidget:
        """创建任务表格"""
        table = QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels([
            "文件名", "类型", "状态", "进度", "错误", "操作"
        ])
        
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.ExtendedSelection)
        table.itemSelectionChanged.connect(self._on_selection_changed)
        
        return table
    
    def _load_tasks(self):
        """加载已保存的任务"""
        tasks = task_store.get_all_tasks()
        for task in tasks:
            self._add_task_to_table(task)
        
        # 启动轮询
        if task_store.get_active_tasks():
            self._start_polling()
    
    def _add_task_to_table(self, task: TaskRecord):
        """添加任务到表格"""
        row = self.task_table.rowCount()
        self.task_table.insertRow(row)
        
        # 文件名
        name_item = QTableWidgetItem(task.get_display_name())
        name_item.setData(Qt.UserRole, task.local_id)
        self.task_table.setItem(row, 0, name_item)
        
        # 类型
        type_text = "批处理" if task.task_type == TaskType.BATCH else "单图"
        self.task_table.setItem(row, 1, QTableWidgetItem(type_text))
        
        # 状态
        status_item = QTableWidgetItem(task.get_status_text())
        self._set_status_color(status_item, task.status)
        self.task_table.setItem(row, 2, status_item)
        
        # 进度
        progress_text = f"{int(task.progress * 100)}%" if task.progress > 0 else "-"
        self.task_table.setItem(row, 3, QTableWidgetItem(progress_text))
        
        # 错误
        error_text = task.error[:50] + "..." if task.error and len(task.error) > 50 else (task.error or "")
        self.task_table.setItem(row, 4, QTableWidgetItem(error_text))
        
        # 操作按钮
        self.task_table.setItem(row, 5, QTableWidgetItem(""))
    
    def _update_task_row(self, task: TaskRecord):
        """更新表格中的任务行"""
        for row in range(self.task_table.rowCount()):
            item = self.task_table.item(row, 0)
            if item and item.data(Qt.UserRole) == task.local_id:
                # 更新状态
                status_item = QTableWidgetItem(task.get_status_text())
                self._set_status_color(status_item, task.status)
                self.task_table.setItem(row, 2, status_item)
                
                # 更新进度
                progress_text = f"{int(task.progress * 100)}%" if task.progress > 0 else "-"
                self.task_table.setItem(row, 3, QTableWidgetItem(progress_text))
                
                # 更新错误
                error_text = task.error[:50] + "..." if task.error and len(task.error) > 50 else (task.error or "")
                self.task_table.setItem(row, 4, QTableWidgetItem(error_text))
                break
    
    def _set_status_color(self, item: QTableWidgetItem, status: TaskStatus):
        """设置状态颜色"""
        colors = {
            TaskStatus.QUEUED: QColor(128, 128, 128),  # 灰色
            TaskStatus.UPLOADING: QColor(100, 149, 237),  # 蓝色
            TaskStatus.PENDING: QColor(128, 128, 128),  # 灰色
            TaskStatus.RUNNING: QColor(30, 144, 255),  # 蓝色
            TaskStatus.SUCCEEDED: QColor(34, 139, 34),  # 绿色
            TaskStatus.FAILED: QColor(220, 20, 60),  # 红色
            TaskStatus.CANCELLED: QColor(255, 140, 0),  # 橙色
            TaskStatus.BATCH_PENDING: QColor(128, 128, 128),
            TaskStatus.BATCH_RUNNING: QColor(30, 144, 255),
            TaskStatus.BATCH_MERGING: QColor(138, 43, 226),  # 紫色
        }
        item.setForeground(colors.get(status, QColor(0, 0, 0)))
    
    # ------------------------------------------------------------------ #
    # 事件处理
    # ------------------------------------------------------------------ #
    
    def _check_server(self):
        """检查服务器连接"""
        try:
            if api_client.health_check():
                meta = api_client.get_meta()
                self.output_dir = meta.output_dir
                self.supports_batch = meta.supports_batch
                
                self.server_status_label.setText(f"服务器: 已连接 (v{meta.version})")
                self.server_status_label.setStyleSheet("color: green;")
                
                self.output_dir_label.setText(f"输出目录: {self.output_dir}")
                self.btn_open_output.setEnabled(True)
                
                self.chk_batch_mode.setEnabled(self.supports_batch)
                if not self.supports_batch:
                    self.chk_batch_mode.setToolTip("服务器未配置批处理支持")
                
                # 处理排队中的任务
                self._process_upload_queue()
            else:
                self._set_server_offline()
        except Exception as e:
            self._set_server_offline()
            self.status_bar.showMessage(f"连接服务器失败: {e}")
    
    def _set_server_offline(self):
        """设置服务器离线状态"""
        self.server_status_label.setText("服务器: 未连接")
        self.server_status_label.setStyleSheet("color: red;")
        self.btn_open_output.setEnabled(False)
    
    def _select_images(self):
        """选择图片文件"""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择图片",
            "",
            "图片文件 (*.png *.jpg *.jpeg);;所有文件 (*.*)"
        )
        
        if not files:
            return
        
        batch_mode = self.chk_batch_mode.isChecked() and len(files) > 1
        
        if batch_mode:
            # 批处理模式：所有图片作为一个任务
            task = task_store.create_task(files, TaskType.BATCH)
            self._add_task_to_table(task)
            self.upload_queue.append(task.local_id)
        else:
            # 单图模式：每张图片一个任务
            for file_path in files:
                task = task_store.create_task([file_path], TaskType.SINGLE)
                self._add_task_to_table(task)
                self.upload_queue.append(task.local_id)
        
        self._process_upload_queue()
        self.status_bar.showMessage(f"已添加 {len(files)} 张图片")
    
    def _process_upload_queue(self):
        """处理上传队列"""
        # 清理已完成的 worker
        self.upload_workers = [w for w in self.upload_workers if w.isRunning()]
        
        # 计算可以启动的新任务数
        max_concurrent = self.spin_concurrent.value()
        available = max_concurrent - len(self.upload_workers)
        
        while available > 0 and self.upload_queue:
            local_id = self.upload_queue.pop(0)
            task = task_store.get_task(local_id)
            
            if task and task.status == TaskStatus.QUEUED:
                worker = UploadWorker(task, self.worker_signals)
                self.upload_workers.append(worker)
                worker.start()
                available -= 1
        
        # 如果有活跃任务，启动轮询
        if task_store.get_active_tasks() or self.upload_workers:
            self._start_polling()
    
    def _start_polling(self):
        """启动轮询定时器"""
        if not self.poll_timer.isActive():
            interval = config.poll_interval_single * 1000
            self.poll_timer.start(interval)
    
    def _stop_polling(self):
        """停止轮询定时器"""
        if self.poll_timer.isActive():
            self.poll_timer.stop()
    
    def _poll_tasks(self):
        """轮询任务状态"""
        active_tasks = task_store.get_active_tasks()
        
        if not active_tasks and not self.upload_workers and not self.upload_queue:
            self._stop_polling()
            return
        
        for task in active_tasks:
            try:
                if task.task_type == TaskType.SINGLE and task.task_id:
                    data = api_client.get_job_status(task.task_id)
                    self._update_single_task(task, data)
                elif task.task_type == TaskType.BATCH and task.batch_id:
                    data = api_client.get_batch_status(task.batch_id)
                    self._update_batch_task(task, data)
            except APIError as e:
                print(f"轮询任务 {task.local_id} 失败: {e}")
        
        # 继续处理上传队列
        self._process_upload_queue()
    
    def _update_single_task(self, task: TaskRecord, data: dict):
        """更新单图任务状态"""
        status_str = data.get("status", "")
        new_status = TaskStatus(status_str) if status_str else task.status
        
        updates = {"status": new_status}
        
        if data.get("result"):
            updates["result"] = data["result"]
            updates["progress"] = 1.0
        
        if data.get("error"):
            updates["error"] = data["error"]
        
        task_store.update_task(task.local_id, **updates)
        self._update_task_row(task_store.get_task(task.local_id))
    
    def _update_batch_task(self, task: TaskRecord, data: dict):
        """更新批处理任务状态"""
        status_str = data.get("status", "")
        new_status = TaskStatus(status_str) if status_str else task.status
        
        total = data.get("total_jobs", 0)
        completed = data.get("completed_jobs", 0)
        failed = data.get("failed_jobs", 0)
        
        progress = completed / total if total > 0 else 0
        
        updates = {
            "status": new_status,
            "total_jobs": total,
            "completed_jobs": completed,
            "failed_jobs": failed,
            "current_round": data.get("round", 0),
            "progress": progress,
        }
        
        task_store.update_task(task.local_id, **updates)
        self._update_task_row(task_store.get_task(task.local_id))
    
    def _on_task_updated(self, local_id: str):
        """任务更新信号处理"""
        task = task_store.get_task(local_id)
        if task:
            self._update_task_row(task)
    
    def _on_upload_finished(self, local_id: str, success: bool, message: str):
        """上传完成信号处理"""
        task = task_store.get_task(local_id)
        if task:
            self._update_task_row(task)
        
        if success:
            self.status_bar.showMessage(f"上传成功: {message}")
        else:
            self.status_bar.showMessage(f"上传失败: {message}")
        
        # 继续处理队列
        self._process_upload_queue()
    
    def _on_error(self, message: str):
        """错误信号处理"""
        QMessageBox.warning(self, "错误", message)
    
    def _on_selection_changed(self):
        """选择变化处理"""
        selected = self.task_table.selectedItems()
        if not selected:
            self.result_text.clear()
            self.process_text.clear()
            return
        
        # 获取第一个选中的任务
        row = selected[0].row()
        item = self.task_table.item(row, 0)
        if not item:
            return
        
        local_id = item.data(Qt.UserRole)
        task = task_store.get_task(local_id)
        if not task:
            return
        
        # 显示结果
        if task.result:
            import json
            self.result_text.setText(json.dumps(task.result, indent=2, ensure_ascii=False))
        else:
            self.result_text.setText("暂无结果")
        
        # 尝试获取处理过程
        self._load_process_info(task)
    
    def _load_process_info(self, task: TaskRecord):
        """加载处理过程信息"""
        self.process_text.clear()
        
        if not task.task_id and not task.session_id:
            self.process_text.setText("暂无处理记录")
            return
        
        try:
            if task.task_id:
                data = api_client.get_job_process(task.task_id)
            elif task.session_id:
                data = api_client.get_process_by_session(task.session_id)
            else:
                return
            
            lines = []
            for round_info in data.get("rounds", []):
                lines.append(f"=== 第 {round_info.get('round_index', '?')} 轮 ===")
                lines.append(f"时间: {round_info.get('timestamp', '-')}")
                lines.append(f"摘要: {round_info.get('summary', '-')}")
                
                tool_calls = round_info.get("tool_calls", [])
                if tool_calls:
                    lines.append("工具调用:")
                    for tc in tool_calls:
                        lines.append(f"  - {tc.get('name', '?')}: {tc.get('result_summary', '-')}")
                lines.append("")
            
            self.process_text.setText("\n".join(lines) if lines else "暂无处理记录")
        except APIError as e:
            self.process_text.setText(f"获取处理记录失败: {e}")
    
    def _on_concurrent_changed(self, value: int):
        """并发数变化处理"""
        config.max_concurrent_uploads = value
        config.save()
    
    # ------------------------------------------------------------------ #
    # 任务操作
    # ------------------------------------------------------------------ #
    
    def _get_selected_tasks(self) -> List[TaskRecord]:
        """获取选中的任务"""
        tasks = []
        for item in self.task_table.selectedItems():
            if item.column() == 0:
                local_id = item.data(Qt.UserRole)
                task = task_store.get_task(local_id)
                if task:
                    tasks.append(task)
        return tasks
    
    def _cancel_selected(self):
        """取消选中的任务"""
        tasks = self._get_selected_tasks()
        cancelled = 0
        
        for task in tasks:
            if not task.can_cancel():
                continue
            
            try:
                if task.task_id:
                    api_client.cancel_job(task.task_id)
                
                task_store.update_task(task.local_id, status=TaskStatus.CANCELLED)
                self._update_task_row(task_store.get_task(task.local_id))
                cancelled += 1
            except APIError as e:
                print(f"取消任务失败: {e}")
        
        self.status_bar.showMessage(f"已取消 {cancelled} 个任务")
    
    def _retry_selected(self):
        """重试选中的任务"""
        tasks = self._get_selected_tasks()
        retried = 0
        
        for task in tasks:
            if not task.can_retry():
                continue
            
            # 重置状态并加入队列
            task_store.update_task(
                task.local_id,
                status=TaskStatus.QUEUED,
                error=None,
                retry_count=task.retry_count + 1,
            )
            self.upload_queue.append(task.local_id)
            self._update_task_row(task_store.get_task(task.local_id))
            retried += 1
        
        if retried > 0:
            self._process_upload_queue()
        
        self.status_bar.showMessage(f"已重试 {retried} 个任务")
    
    def _view_selected_result(self):
        """查看选中任务的结果"""
        tasks = self._get_selected_tasks()
        if not tasks:
            return
        
        task = tasks[0]
        if not task.result:
            QMessageBox.information(self, "提示", "该任务暂无结果")
            return
        
        # 切换到结果详情标签
        self.detail_tabs.setCurrentIndex(0)
    
    def _clear_completed(self):
        """清除已完成的任务"""
        count = task_store.clear_completed()
        
        # 从表格中移除
        rows_to_remove = []
        for row in range(self.task_table.rowCount()):
            item = self.task_table.item(row, 0)
            if item:
                local_id = item.data(Qt.UserRole)
                if not task_store.get_task(local_id):
                    rows_to_remove.append(row)
        
        for row in reversed(rows_to_remove):
            self.task_table.removeRow(row)
        
        self.status_bar.showMessage(f"已清除 {count} 个已完成任务")
    
    def _refresh_all(self):
        """刷新所有任务状态"""
        self._check_server()
        self._poll_tasks()
        self.status_bar.showMessage("已刷新")
    
    def _open_output_dir(self):
        """打开输出目录"""
        if not self.output_dir:
            return
        
        path = Path(self.output_dir)
        if not path.exists():
            QMessageBox.warning(self, "错误", f"目录不存在: {self.output_dir}")
            return
        
        # Windows
        if sys.platform == "win32":
            os.startfile(str(path))
        # macOS
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)])
        # Linux
        else:
            subprocess.run(["xdg-open", str(path)])
    
    def _change_output_dir(self):
        """更改输出目录"""
        # 获取当前目录作为起始目录
        start_dir = self.output_dir or str(Path.home())
        
        # 打开文件夹选择对话框
        new_dir = QFileDialog.getExistingDirectory(
            self,
            "选择结果保存目录",
            start_dir,
            QFileDialog.ShowDirsOnly
        )
        
        if not new_dir:
            return
        
        # 更新 .env 文件
        env_path = Path(__file__).parent.parent / ".env"
        
        try:
            # 读取现有内容
            env_content = ""
            if env_path.exists():
                env_content = env_path.read_text(encoding="utf-8")
            
            # 更新或添加 OUTPUT_DIR
            lines = env_content.splitlines()
            found = False
            new_lines = []
            
            for line in lines:
                if line.strip().startswith("OUTPUT_DIR="):
                    new_lines.append(f"OUTPUT_DIR={new_dir}")
                    found = True
                else:
                    new_lines.append(line)
            
            if not found:
                new_lines.append(f"\n# Output directory")
                new_lines.append(f"OUTPUT_DIR={new_dir}")
            
            # 写入文件
            env_path.write_text("\n".join(new_lines), encoding="utf-8")
            
            # 提示用户
            QMessageBox.information(
                self,
                "设置成功",
                f"输出目录已更改为:\n{new_dir}\n\n请重启后端服务 (run_server.bat) 使设置生效。"
            )
            
            # 更新显示
            self.output_dir = new_dir
            self.output_dir_label.setText(f"输出目录: {new_dir}")
            self.btn_open_output.setEnabled(True)
            
        except Exception as e:
            QMessageBox.warning(self, "错误", f"更新配置文件失败: {e}")
    
    def closeEvent(self, event):
        """关闭窗口事件"""
        # 停止所有 worker
        for worker in self.upload_workers:
            if worker.isRunning():
                worker.terminate()
                worker.wait()
        
        self._stop_polling()
        event.accept()


def main():
    """主函数"""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

