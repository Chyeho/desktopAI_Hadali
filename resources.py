"""
资源目录管理模块

为项目提供统一的资源路径常量，并处理第三方依赖包的导入路径。
Live2D 模型、贴图等静态资源统一放在 Resources 目录下。
"""
import os
import sys

# 当前文件所在目录（即本项目根目录）
CURRENT_DIRECTORY = os.path.split(__file__)[0]

# 资源根目录：存放 Live2D 模型（.model3.json/.moc3/贴图/动作）等静态资源
RESOURCES_DIRECTORY = os.path.join(CURRENT_DIRECTORY, "Resources")

# 如果存在本地打包目录 package，则将其加入模块搜索路径，
# 供 live2d 等第三方库依赖的二进制文件（如 DLL）使用
_package_dir = os.path.join(CURRENT_DIRECTORY, "package")
if _package_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_package_dir))
