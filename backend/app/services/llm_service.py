"""LLM service for video summarization"""
import httpx
from typing import Optional, Dict, Any
import logging
from app.config import settings

logger = logging.getLogger(__name__)


class LLMService:
    """LLM service for generating summaries"""
    
    def __init__(self):
        self.ollama_url = settings.ollama_url
        self.vllm_url = settings.vllm_url
        self.model = settings.llm_model
        self.use_vllm = bool(self.vllm_url)
    
    async def format_transcript(self, transcript: str, language: str = "中文") -> str:
        """
        Format transcript using LLM - add punctuation and organize into paragraphs
        
        Args:
            transcript: Raw transcript text without punctuation
            language: Language of the transcript
            
        Returns:
            Formatted transcript with punctuation and paragraphs
        """
        if self.use_vllm:
            return await self._format_with_vllm(transcript, language)
        else:
            return await self._format_with_ollama(transcript, language)
    
    async def generate_summary(self, transcript: str, language: str = "中文") -> str:
        """
        Generate video summary using LLM
        
        Args:
            transcript: Video transcript text
            language: Language of the transcript
            
        Returns:
            Generated summary text
        """
        if self.use_vllm:
            return await self._generate_with_vllm(transcript, language)
        else:
            return await self._generate_with_ollama(transcript, language)
    
    async def generate_keywords(self, transcript: str, title: str = "", language: str = "中文") -> str:
        """
        Generate keywords from video transcript and title using LLM
        
        Args:
            transcript: Video transcript text
            title: Video title (optional)
            language: Language of the transcript
            
        Returns:
            Comma-separated keywords string
        """
        if self.use_vllm:
            return await self._generate_keywords_with_vllm(transcript, title, language)
        else:
            return await self._generate_keywords_with_ollama(transcript, title, language)
    
    async def _format_with_ollama(self, transcript: str, language: str) -> str:
        """Format transcript using Ollama"""
        try:
            # Process in chunks if transcript is too long
            max_length = 12000  # Approximate token limit for formatting
            if len(transcript) <= max_length:
                return await self._format_chunk_with_ollama(transcript, language)
            else:
                # Split into chunks and format each
                chunks = []
                chunk_size = max_length
                for i in range(0, len(transcript), chunk_size):
                    chunk = transcript[i:i + chunk_size]
                    formatted_chunk = await self._format_chunk_with_ollama(chunk, language)
                    chunks.append(formatted_chunk)
                return "\n\n".join(chunks)
        except Exception as e:
            logger.error(f"Error formatting transcript with Ollama: {e}")
            # Return original transcript if formatting fails
            return transcript
    
    async def _format_chunk_with_ollama(self, transcript: str, language: str) -> str:
        """Format a single chunk of transcript using Ollama"""
        prompt = f"""请为以下视频转录内容添加标点符号并分段落整理。转录内容使用{language}。

要求：
1. 添加适当的标点符号（句号、逗号、问号、感叹号等）
2. 根据语义和停顿，将内容分成多个段落
3. 每个段落应该表达一个完整的意思
4. 保持原文内容不变，只添加标点符号和分段
5. 使用{language}回复

转录内容：
{transcript}

请整理后的内容："""
        
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                }
            )
            response.raise_for_status()
            result = response.json()
            formatted = result.get("response", transcript)
            # Clean up the response (remove prompt echo if any)
            if formatted.startswith(transcript[:50]):
                # Response might include the prompt, extract only the formatted part
                lines = formatted.split("\n")
                # Find the line that starts with the actual formatted content
                for i, line in enumerate(lines):
                    if line.strip() and not line.strip().startswith("请") and not line.strip().startswith("转录"):
                        return "\n".join(lines[i:])
            return formatted
    
    async def _format_with_vllm(self, transcript: str, language: str) -> str:
        """Format transcript using vLLM API"""
        try:
            # Process in chunks if transcript is too long
            max_length = 12000
            if len(transcript) <= max_length:
                return await self._format_chunk_with_vllm(transcript, language)
            else:
                # Split into chunks and format each
                chunks = []
                chunk_size = max_length
                for i in range(0, len(transcript), chunk_size):
                    chunk = transcript[i:i + chunk_size]
                    formatted_chunk = await self._format_chunk_with_vllm(chunk, language)
                    chunks.append(formatted_chunk)
                return "\n\n".join(chunks)
        except Exception as e:
            logger.error(f"Error formatting transcript with vLLM: {e}")
            # Return original transcript if formatting fails
            return transcript
    
    async def _format_chunk_with_vllm(self, transcript: str, language: str) -> str:
        """Format a single chunk of transcript using vLLM"""
        prompt = f"""请为以下视频转录内容添加标点符号并分段落整理。转录内容使用{language}。

要求：
1. 添加适当的标点符号（句号、逗号、问号、感叹号等）
2. 根据语义和停顿，将内容分成多个段落
3. 每个段落应该表达一个完整的意思
4. 保持原文内容不变，只添加标点符号和分段
5. 使用{language}回复

转录内容：
{transcript}

请整理后的内容："""
        
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"{self.vllm_url}/v1/completions",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "max_tokens": len(transcript) + 1000,  # Allow for added punctuation
                    "temperature": 0.3,  # Lower temperature for more consistent formatting
                }
            )
            response.raise_for_status()
            result = response.json()
            choices = result.get("choices", [])
            if choices:
                formatted = choices[0].get("text", transcript)
                # Clean up the response
                if formatted.startswith(transcript[:50]):
                    lines = formatted.split("\n")
                    for i, line in enumerate(lines):
                        if line.strip() and not line.strip().startswith("请") and not line.strip().startswith("转录"):
                            return "\n".join(lines[i:])
                return formatted
            return transcript
    
    async def _generate_with_ollama(self, transcript: str, language: str) -> str:
        """Generate summary using Ollama"""
        try:
            # Truncate transcript if too long (Ollama has context limits)
            max_length = 8000  # Approximate token limit
            if len(transcript) > max_length:
                transcript = transcript[:max_length] + "..."
            
            prompt = f"""请为以下视频转录内容生成一个简洁的总结。转录内容使用{language}。

要求：
1. 总结应该简洁明了，突出主要内容
2. 如果内容较长，可以分段总结
3. 使用{language}回复

转录内容：
{transcript}

请生成总结："""
            
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                    }
                )
                response.raise_for_status()
                result = response.json()
                return result.get("response", "生成总结失败")
                
        except httpx.TimeoutException:
            logger.error("Ollama request timeout")
            raise Exception("LLM请求超时，请稍后重试")
        except httpx.RequestError as e:
            logger.error(f"Ollama request error: {e}")
            raise Exception(f"LLM请求失败: {str(e)}")
        except Exception as e:
            logger.error(f"Error generating summary with Ollama: {e}")
            raise Exception(f"生成总结失败: {str(e)}")
    
    async def _generate_with_vllm(self, transcript: str, language: str) -> str:
        """Generate summary using vLLM API"""
        try:
            # Truncate transcript if too long
            max_length = 8000
            if len(transcript) > max_length:
                transcript = transcript[:max_length] + "..."
            
            prompt = f"""请为以下视频转录内容生成一个简洁的总结。转录内容使用{language}。

要求：
1. 总结应该简洁明了，突出主要内容
2. 如果内容较长，可以分段总结
3. 使用{language}回复

转录内容：
{transcript}

请生成总结："""
            
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    f"{self.vllm_url}/v1/completions",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "max_tokens": 1000,
                        "temperature": 0.7,
                    }
                )
                response.raise_for_status()
                result = response.json()
                choices = result.get("choices", [])
                if choices:
                    return choices[0].get("text", "生成总结失败")
                return "生成总结失败"
                
        except Exception as e:
            logger.error(f"Error generating summary with vLLM: {e}")
            raise Exception(f"生成总结失败: {str(e)}")
    
    async def _generate_keywords_with_ollama(self, transcript: str, title: str, language: str) -> str:
        """Generate keywords using Ollama"""
        try:
            # Use transcript and title for keyword generation
            content = f"标题: {title}\n\n" if title else ""
            # Truncate transcript if too long
            max_length = 6000
            if len(transcript) > max_length:
                content += transcript[:max_length] + "..."
            else:
                content += transcript
            
            prompt = f"""请为以下视频内容提取关键词。转录内容使用{language}。

要求：
1. 提取5-10个最重要的关键词
2. 关键词应该能够概括视频的主要内容
3. 关键词之间用逗号分隔
4. 只返回关键词，不要其他说明文字
5. 使用{language}回复

视频内容：
{content}

关键词："""
            
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                    }
                )
                response.raise_for_status()
                result = response.json()
                keywords_text = result.get("response", "").strip()
                
                # Clean up the response - extract only keywords
                # Remove any prefix text before keywords
                lines = keywords_text.split("\n")
                keywords_line = ""
                for line in lines:
                    line = line.strip()
                    # Skip empty lines and instruction lines
                    if line and not line.startswith("请") and not line.startswith("关键词") and not line.startswith("要求"):
                        # Check if line contains commas (likely the keywords)
                        if "," in line or "，" in line:
                            keywords_line = line
                            break
                        # If no comma found, use the first non-empty line
                        if not keywords_line:
                            keywords_line = line
                
                # Normalize separators (handle both comma types)
                keywords_line = keywords_line.replace("，", ",")
                # Remove any trailing punctuation
                keywords_line = keywords_line.rstrip(".,。，")
                
                return keywords_line if keywords_line else ""
                
        except httpx.TimeoutException:
            logger.error("Ollama keywords request timeout")
            return ""
        except httpx.RequestError as e:
            logger.error(f"Ollama keywords request error: {e}")
            return ""
        except Exception as e:
            logger.error(f"Error generating keywords with Ollama: {e}")
            return ""
    
    async def _generate_keywords_with_vllm(self, transcript: str, title: str, language: str) -> str:
        """Generate keywords using vLLM API"""
        try:
            content = f"标题: {title}\n\n" if title else ""
            max_length = 6000
            if len(transcript) > max_length:
                content += transcript[:max_length] + "..."
            else:
                content += transcript
            
            prompt = f"""请为以下视频内容提取关键词。转录内容使用{language}。

要求：
1. 提取5-10个最重要的关键词
2. 关键词应该能够概括视频的主要内容
3. 关键词之间用逗号分隔
4. 只返回关键词，不要其他说明文字
5. 使用{language}回复

视频内容：
{content}

关键词："""
            
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.vllm_url}/v1/completions",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "max_tokens": 200,
                        "temperature": 0.5,
                    }
                )
                response.raise_for_status()
                result = response.json()
                choices = result.get("choices", [])
                if choices:
                    keywords_text = choices[0].get("text", "").strip()
                    
                    # Clean up the response
                    lines = keywords_text.split("\n")
                    keywords_line = ""
                    for line in lines:
                        line = line.strip()
                        if line and not line.startswith("请") and not line.startswith("关键词") and not line.startswith("要求"):
                            if "," in line or "，" in line:
                                keywords_line = line
                                break
                            if not keywords_line:
                                keywords_line = line
                    
                    keywords_line = keywords_line.replace("，", ",")
                    keywords_line = keywords_line.rstrip(".,。，")
                    
                    return keywords_line if keywords_line else ""
                return ""
                
        except Exception as e:
            logger.error(f"Error generating keywords with vLLM: {e}")
            return ""
