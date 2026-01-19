"""
title: Fix Markdown Filter
author: OpenWebUI User
version: 0.1.0
description: 修复 OpenWebUI 中的 Markdown 格式异常，包括移除 Claude 的 antArtifact 标签等
"""

import re
from typing import Optional


class Filter:
    def __init__(self):
        pass

    def inlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        """入口过滤器 - 处理用户输入（如需要）"""
        return body

    def outlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        """出口过滤器 - 处理模型输出"""
        # 获取消息列表
        messages = body.get("messages", [])
        
        # 处理最后一条助手消息
        for message in reversed(messages):
            if message.get("role") == "assistant":
                content = message.get("content", "")
                if isinstance(content, str):
                    message["content"] = self.fix_markdown(content)
                break
        
        return body

    def fix_markdown(self, content: str) -> str:
        """
        修复 Markdown 格式异常
        
        目前支持的修复：
        1. 移除 Claude 的 <antArtifact> 标签
        2. 移除 Claude 的 <antThinking> 标签
        """
        if not content:
            return content
        
        # 1. 移除 <antArtifact> 标签（保留内部内容）
        content = self._remove_ant_artifact_tags(content)
        
        # 2. 移除 <antThinking> 标签及其内容（思考过程通常不需要显示）
        content = self._remove_ant_thinking_tags(content)
        
        return content.strip()

    def _remove_ant_artifact_tags(self, content: str) -> str:
        """
        移除 <antArtifact> 标签，保留内部的 markdown 内容
        
        示例输入:
        <antArtifact type="text/markdown" identifier="xxx" title="标题">
        # 实际内容
        </antArtifact>
        
        输出:
        # 实际内容
        """
        # 匹配开始标签: <antArtifact ...>
        # 使用非贪婪匹配处理多行属性
        pattern_start = r'<antArtifact[^>]*>'
        content = re.sub(pattern_start, '', content, flags=re.IGNORECASE | re.DOTALL)
        
        # 匹配结束标签: </antArtifact>
        pattern_end = r'</antArtifact>'
        content = re.sub(pattern_end, '', content, flags=re.IGNORECASE)
        
        return content

    def _remove_ant_thinking_tags(self, content: str) -> str:
        """
        移除 <antThinking> 标签及其全部内容
        
        思考过程通常不需要展示给用户
        """
        # 匹配 <antThinking>...</antThinking> 及其内容
        pattern = r'<antThinking>.*?</antThinking>'
        content = re.sub(pattern, '', content, flags=re.IGNORECASE | re.DOTALL)
        
        return content
