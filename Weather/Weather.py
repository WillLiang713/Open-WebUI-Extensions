"""
title: 高德天气查询工具
author: @WillLiang713
description: 使用高德开放平台API获取指定城市的实时天气或天气预报
version: 1.0.0
required_open_webui_version: >= 0.6.0
"""

import json
from typing import Optional
import aiohttp
from pydantic import BaseModel, Field


class Tools:
    class Valves(BaseModel):
        AMAP_API_KEY: str = Field(
            default="",
            description="高德开放平台Web服务API Key，请在 https://console.amap.com 申请",
        )

    def __init__(self):
        self.valves = self.Valves()
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "获取指定城市的天气信息。可以查询实时天气或未来几天的天气预报。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "city": {
                                "type": "string",
                                "description": "城市名称，如：北京、上海、广州、深圳等。工具会自动尝试匹配城市编码。也可以直接输入城市的adcode编码。",
                            },
                            "forecast": {
                                "type": "boolean",
                                "description": "是否获取天气预报。为true时返回未来几天的天气预报，为false时只返回实时天气。默认为false。",
                            },
                        },
                        "required": ["city"],
                    },
                },
            }
        ]

    # 常用城市 adcode 映射表（可扩展）
    CITY_ADCODE_MAP = {
        # 直辖市
        "北京": "110000",
        "上海": "310000",
        "天津": "120000",
        "重庆": "500000",
        # 省会城市
        "广州": "440100",
        "深圳": "440300",
        "杭州": "330100",
        "南京": "320100",
        "武汉": "420100",
        "成都": "510100",
        "西安": "610100",
        "郑州": "410100",
        "长沙": "430100",
        "济南": "370100",
        "青岛": "370200",
        "大连": "210200",
        "沈阳": "210100",
        "哈尔滨": "230100",
        "长春": "220100",
        "福州": "350100",
        "厦门": "350200",
        "昆明": "530100",
        "贵阳": "520100",
        "南宁": "450100",
        "海口": "460100",
        "合肥": "340100",
        "石家庄": "130100",
        "太原": "140100",
        "呼和浩特": "150100",
        "兰州": "620100",
        "银川": "640100",
        "西宁": "630100",
        "乌鲁木齐": "650100",
        "拉萨": "540100",
        "南昌": "360100",
        # 其他热门城市
        "苏州": "320500",
        "无锡": "320200",
        "常州": "320400",
        "宁波": "330200",
        "温州": "330300",
        "东莞": "441900",
        "佛山": "440600",
        "珠海": "440400",
        "中山": "442000",
        "惠州": "441300",
        "泉州": "350500",
        "烟台": "370600",
        "威海": "371000",
        "潍坊": "370700",
        "淄博": "370300",
        "台北": "710100",
        "香港": "810000",
        "澳门": "820000",
    }

    def _get_adcode(self, city: str) -> str:
        """获取城市的adcode编码"""
        # 如果输入的就是数字（adcode），直接返回
        if city.isdigit():
            return city
        
        # 尝试从映射表中查找
        # 先尝试完全匹配
        if city in self.CITY_ADCODE_MAP:
            return self.CITY_ADCODE_MAP[city]
        
        # 尝试模糊匹配（城市名包含输入）
        for city_name, adcode in self.CITY_ADCODE_MAP.items():
            if city in city_name or city_name in city:
                return adcode
        
        # 如果都没找到，返回原始输入，让API尝试处理
        return city

    def _format_live_weather(self, data: dict) -> str:
        """格式化实时天气数据"""
        # 检查是否已经是格式化后的数据（防止重复处理）
        if "类型" in data and "天气" in data:
            return json.dumps(data, ensure_ascii=False, indent=2)
        
        if data.get("status") != "1":
            error_info = data.get('info') or '未知错误'
            error_code = data.get('infocode', '')
            return json.dumps({
                "error": f"查询失败：{error_info}",
                "错误码": error_code,
                "原始响应": data
            }, ensure_ascii=False, indent=2)
        
        lives = data.get("lives", [])
        if not lives:
            return json.dumps({
                "error": "未获取到天气数据",
                "原始响应": data
            }, ensure_ascii=False, indent=2)
        
        weather = lives[0]
        return json.dumps({
            "类型": "实时天气",
            "省份": weather.get("province", ""),
            "城市": weather.get("city", ""),
            "天气": weather.get("weather", ""),
            "温度": f"{weather.get('temperature', '')}°C",
            "风向": weather.get("winddirection", ""),
            "风力": f"{weather.get('windpower', '')}级",
            "湿度": f"{weather.get('humidity', '')}%",
            "更新时间": weather.get("reporttime", ""),
        }, ensure_ascii=False, indent=2)

    def _format_forecast_weather(self, data: dict) -> str:
        """格式化天气预报数据"""
        # 检查是否已经是格式化后的数据（防止重复处理）
        if "类型" in data and "预报" in data:
            return json.dumps(data, ensure_ascii=False, indent=2)
        
        if data.get("status") != "1":
            error_info = data.get('info') or '未知错误'
            error_code = data.get('infocode', '')
            return json.dumps({
                "error": f"查询失败：{error_info}",
                "错误码": error_code,
                "原始响应": data
            }, ensure_ascii=False, indent=2)
        
        forecasts = data.get("forecasts", [])
        if not forecasts:
            return json.dumps({
                "error": "未获取到天气预报数据",
                "原始响应": data
            }, ensure_ascii=False, indent=2)
        
        forecast = forecasts[0]
        casts = forecast.get("casts", [])
        
        result = {
            "类型": "天气预报",
            "省份": forecast.get("province", ""),
            "城市": forecast.get("city", ""),
            "更新时间": forecast.get("reporttime", ""),
            "预报": []
        }
        
        for cast in casts:
            day_info = {
                "日期": cast.get("date", ""),
                "星期": f"星期{cast.get('week', '')}",
                "白天天气": cast.get("dayweather", ""),
                "夜间天气": cast.get("nightweather", ""),
                "白天温度": f"{cast.get('daytemp', '')}°C",
                "夜间温度": f"{cast.get('nighttemp', '')}°C",
                "白天风向": cast.get("daywind", ""),
                "夜间风向": cast.get("nightwind", ""),
                "白天风力": f"{cast.get('daypower', '')}级",
                "夜间风力": f"{cast.get('nightpower', '')}级",
            }
            result["预报"].append(day_info)
        
        return json.dumps(result, ensure_ascii=False, indent=2)

    async def get_weather(
        self,
        city: str,
        forecast: bool = False,
        __event_emitter__: Optional[object] = None,
        __user__: Optional[dict] = None,
    ) -> str:
        """
        获取指定城市的天气信息
        
        Args:
            city: 城市名称或adcode编码
            forecast: 是否获取天气预报，默认False只获取实时天气
        
        Returns:
            天气信息的JSON字符串
        """
        # 检查API Key
        if not self.valves.AMAP_API_KEY:
            return json.dumps({
                "error": "请先配置高德开放平台API Key",
                "说明": "请在工具设置中填入您的高德Web服务API Key，可在 https://console.amap.com 申请"
            }, ensure_ascii=False)
        
        # 获取城市adcode
        adcode = self._get_adcode(city)
        
        # 构建请求URL
        base_url = "https://restapi.amap.com/v3/weather/weatherInfo"
        params = {
            "key": self.valves.AMAP_API_KEY,
            "city": adcode,
            "extensions": "all" if forecast else "base",
            "output": "JSON"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(base_url, params=params) as response:
                    if response.status != 200:
                        return json.dumps({
                            "error": f"请求失败，HTTP状态码：{response.status}"
                        }, ensure_ascii=False)
                    
                    data = await response.json()
                    
                    # 检查API返回状态
                    if data.get("status") != "1":
                        return json.dumps({
                            "error": f"API返回错误：{data.get('info', '未知错误')}",
                            "infocode": data.get("infocode", ""),
                            "提示": "请检查城市名称是否正确，或者API Key是否有效"
                        }, ensure_ascii=False)
                    
                    # 格式化并返回结果
                    if forecast:
                        return self._format_forecast_weather(data)
                    else:
                        return self._format_live_weather(data)
                        
        except aiohttp.ClientError as e:
            return json.dumps({
                "error": f"网络请求错误：{str(e)}"
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({
                "error": f"发生错误：{str(e)}"
            }, ensure_ascii=False)
