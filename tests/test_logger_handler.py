"""单元测试：日志管理 utils/logger_handler.py

覆盖 get_logger 的幂等性与处理器配置。
"""
import logging

from utils.logger_handler import get_logger, logger


class TestGetLogger:
    """get_logger：创建/复用日志器"""

    def test_module_logger_exists(self):
        assert logger is not None
        assert isinstance(logger, logging.Logger)

    def test_idempotent_handlers(self):
        """多次调用不应重复创建处理器"""
        log1 = get_logger("test_idempotent")
        handler_count = len(log1.handlers)
        log2 = get_logger("test_idempotent")
        assert log1 is log2
        assert len(log2.handlers) == handler_count

    def test_custom_name(self):
        log = get_logger("test_custom_name")
        assert log.name == "test_custom_name"

    def test_has_console_handler(self):
        log = get_logger("test_console")
        console_handlers = [h for h in log.handlers if isinstance(h, logging.StreamHandler)]
        assert len(console_handlers) >= 1

    def test_has_file_handler(self):
        log = get_logger("test_file")
        file_handlers = [h for h in log.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) >= 1

    def test_log_levels(self):
        """日志器总级别为 DEBUG（允许所有级别输出到处理器）"""
        log = get_logger("test_levels")
        assert log.level == logging.DEBUG
