"""
NovelAI图片生成服务 - 空间插件专用
独立实现，不依赖其他插件
"""
import asyncio
import base64
import random
import uuid
import zipfile
import io
from pathlib import Path
from typing import Optional

import aiohttp
from PIL import Image

from src.common.logger import get_logger

logger = get_logger("MaiZone.NovelAIService")


class MaiZoneNovelAIService:
    """空间插件的NovelAI图片生成服务（独立实现）"""
    
    def __init__(self, get_config):
        self.get_config = get_config
        
        # NovelAI配置
        self.api_key = self.get_config("novelai.api_key", "")
        self.base_url = "https://image.novelai.net/ai/generate-image"
        self.model = "nai-diffusion-4-5-full"
        
        # 代理配置
        proxy_host = self.get_config("novelai.proxy_host", "")
        proxy_port = self.get_config("novelai.proxy_port", 0)
        self.proxy = f"http://{proxy_host}:{proxy_port}" if proxy_host and proxy_port else ""
        
        # 生成参数
        self.steps = 28
        self.scale = 5.0
        self.sampler = "k_euler"
        self.noise_schedule = "karras"
        
        # 角色提示词（当LLM决定包含角色时使用）
        self.character_prompt = self.get_config("novelai.character_prompt", "")
        self.base_negative_prompt = self.get_config("novelai.base_negative_prompt", "nsfw, nude, explicit, sexual content, lowres, bad anatomy, bad hands")
        
        # 图片保存目录（使用统一配置）
        plugin_dir = Path(__file__).parent.parent
        self.image_dir = plugin_dir / "images"
        self.image_dir.mkdir(parents=True, exist_ok=True)
        
        if self.api_key:
            logger.info(f"NovelAI图片生成已配置，模型: {self.model}")
    
    def is_available(self) -> bool:
        """检查NovelAI服务是否可用"""
        return bool(self.api_key)
    
    async def generate_image_from_prompt_data(
        self,
        prompt: str,
        negative_prompt: Optional[str] = None,
        include_character: bool = False,
        width: int = 1024,
        height: int = 1024
    ) -> tuple[bool, Optional[Path], str]:
        """根据提示词生成图片
        
        Args:
            prompt: NovelAI格式的英文提示词
            negative_prompt: LLM生成的负面提示词（可选）
            include_character: 是否包含角色形象
            width: 图片宽度
            height: 图片高度
        
        Returns:
            (是否成功, 图片路径, 消息)
        """
        if not self.api_key:
            return False, None, "NovelAI API Key未配置"
        
        try:
            # 处理角色提示词
            final_prompt = prompt
            if include_character and self.character_prompt:
                final_prompt = f"{self.character_prompt}, {prompt}"
                logger.info(f"包含角色形象，添加角色提示词")
            
            # 合并负面提示词
            final_negative = self.base_negative_prompt
            if negative_prompt:
                if final_negative:
                    final_negative = f"{final_negative}, {negative_prompt}"
                else:
                    final_negative = negative_prompt
            
            logger.info(f"🎨 开始生成图片...")
            logger.info(f"  尺寸: {width}x{height}")
            logger.info(f"  正面提示词: {final_prompt[:100]}...")
            logger.info(f"  负面提示词: {final_negative[:100]}...")
            
            # 构建请求payload
            payload = self._build_payload(final_prompt, final_negative, width, height)
            
            # 发送请求
            image_data = await self._call_novelai_api(payload)
            if not image_data:
                return False, None, "API请求失败"
            
            # 保存图片
            image_path = await self._save_image(image_data)
            if not image_path:
                return False, None, "图片保存失败"
            
            logger.info(f"✅ 图片生成成功: {image_path}")
            return True, image_path, "生成成功"
            
        except Exception as e:
            logger.error(f"生成图片时出错: {e}", exc_info=True)
            return False, None, f"生成失败: {str(e)}"
    
    def _build_payload(self, prompt: str, negative_prompt: str, width: int, height: int) -> dict:
        """构建NovelAI API请求payload"""
        is_v4_model = "diffusion-4" in self.model
        is_v3_model = "diffusion-3" in self.model
        
        parameters = {
            "width": width,
            "height": height,
            "scale": self.scale,
            "steps": self.steps,
            "sampler": self.sampler,
            "seed": random.randint(0, 9999999999),
            "n_samples": 1,
            "ucPreset": 0,
            "qualityToggle": True,
            "sm": False,
            "sm_dyn": False,
            "noise_schedule": self.noise_schedule if is_v4_model else "native",
        }
        
        # V4.5模型使用新格式
        if is_v4_model:
            parameters.update({
                "params_version": 3,
                "cfg_rescale": 0,
                "autoSmea": False,
                "legacy": False,
                "legacy_v3_extend": False,
                "legacy_uc": False,
                "add_original_image": True,
                "controlnet_strength": 1,
                "dynamic_thresholding": False,
                "prefer_brownian": True,
                "normalize_reference_strength_multiple": True,
                "use_coords": True,
                "inpaintImg2ImgStrength": 1,
                "deliberate_euler_ancestral_bug": False,
                "skip_cfg_above_sigma": None,
                "characterPrompts": [],
                "stream": "msgpack",
                "v4_prompt": {
                    "caption": {
                        "base_caption": prompt,
                        "char_captions": []
                    },
                    "use_coords": True,
                    "use_order": True
                },
                "v4_negative_prompt": {
                    "caption": {
                        "base_caption": negative_prompt,
                        "char_captions": []
                    },
                    "legacy_uc": False
                },
                "negative_prompt": negative_prompt,
                "reference_image_multiple": [],
                "reference_information_extracted_multiple": [],
                "reference_strength_multiple": []
            })
        # V3使用negative_prompt字段
        elif is_v3_model:
            parameters["negative_prompt"] = negative_prompt
        
        payload = {
            "input": prompt,
            "model": self.model,
            "action": "generate",
            "parameters": parameters
        }
        
        # V4.5需要额外字段
        if is_v4_model:
            payload["use_new_shared_trial"] = True
        
        return payload
    
    async def _call_novelai_api(self, payload: dict) -> Optional[bytes]:
        """调用NovelAI API"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        connector = None
        request_kwargs = {
            "json": payload,
            "headers": headers,
            "timeout": aiohttp.ClientTimeout(total=120)
        }
        
        if self.proxy:
            request_kwargs["proxy"] = self.proxy
            connector = aiohttp.TCPConnector()
            logger.info(f"使用代理: {self.proxy}")
        
        try:
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.post(self.base_url, **request_kwargs) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"API请求失败 ({resp.status}): {error_text[:200]}")
                        return None
                    
                    img_data = await resp.read()
                    logger.info(f"收到响应数据: {len(img_data)} bytes")
                    
                    # 检查是否是ZIP文件
                    if img_data[:4] == b'PK\x03\x04':
                        logger.info("检测到ZIP格式，解压中...")
                        return self._extract_from_zip(img_data)
                    elif img_data[:4] == b'\x89PNG':
                        logger.info("检测到PNG格式")
                        return img_data
                    else:
                        logger.warning(f"未知文件格式，前4字节: {img_data[:4].hex()}")
                        return img_data
        
        except Exception as e:
            logger.error(f"API调用失败: {e}", exc_info=True)
            return None
    
    def _extract_from_zip(self, zip_data: bytes) -> Optional[bytes]:
        """从ZIP中提取PNG"""
        try:
            with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
                for filename in zf.namelist():
                    if filename.lower().endswith('.png'):
                        img_data = zf.read(filename)
                        logger.info(f"从ZIP提取: {filename} ({len(img_data)} bytes)")
                        return img_data
            logger.error("ZIP中未找到PNG文件")
            return None
        except Exception as e:
            logger.error(f"解压ZIP失败: {e}")
            return None
    
    async def _save_image(self, image_data: bytes) -> Optional[Path]:
        """保存图片到本地"""
        try:
            filename = f"novelai_{uuid.uuid4().hex[:12]}.png"
            filepath = self.image_dir / filename
            
            # 写入文件
            with open(filepath, "wb") as f:
                f.write(image_data)
                f.flush()
                import os
                os.fsync(f.fileno())
            
            # 验证图片
            try:
                with Image.open(filepath) as img:
                    img.verify()
                with Image.open(filepath) as img:
                    logger.info(f"图片验证成功: {img.format} {img.size}")
            except Exception as e:
                logger.warning(f"图片验证失败: {e}")
            
            return filepath
            
        except Exception as e:
            logger.error(f"保存图片失败: {e}")
            return None
