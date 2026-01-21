"""Markdown export service"""
from typing import Dict, Any
from datetime import datetime
import re


class MarkdownExporter:
    """Export video records to Markdown format"""
    
    @staticmethod
    def export(video_record: Dict[str, Any], include_timestamps: bool = False) -> str:
        """
        Export video record to Markdown
        
        Args:
            video_record: Video record dict with title, url, summary, transcript, etc.
            include_timestamps: Whether to include timestamps in transcript
            
        Returns:
            Markdown formatted string
        """
        title = video_record.get('title', 'Untitled Video')
        url = video_record.get('url', '')
        summary = video_record.get('summary', '')
        transcript = video_record.get('transcript', '')
        language = video_record.get('language', '')
        created_at = video_record.get('created_at', '')
        segments = video_record.get('segments', [])
        
        # Format date
        if created_at:
            if isinstance(created_at, str):
                try:
                    dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    date_str = dt.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    date_str = created_at
            else:
                date_str = created_at.strftime('%Y-%m-%d %H:%M:%S')
        else:
            date_str = 'Unknown'
        
        # Build Markdown
        md_lines = []
        
        # Title
        md_lines.append(f"# {title}\n")
        
        # Metadata
        md_lines.append("## 视频信息\n")
        md_lines.append(f"- **URL**: {url}")
        md_lines.append(f"- **处理日期**: {date_str}")
        if language:
            md_lines.append(f"- **语言**: {language}")
        md_lines.append("")
        
        # Summary
        if summary:
            md_lines.append("## 视频总结\n")
            md_lines.append(summary)
            md_lines.append("")
        
        # Transcript
        if transcript:
            md_lines.append("## 完整转录\n")
            
            if include_timestamps and segments:
                # Include timestamps
                for segment in segments:
                    start = segment.get('start', 0)
                    end = segment.get('end', 0)
                    text = segment.get('text', '')
                    
                    start_str = MarkdownExporter._format_timestamp(start)
                    end_str = MarkdownExporter._format_timestamp(end)
                    
                    md_lines.append(f"**[{start_str} - {end_str}]** {text}\n")
            else:
                # Plain transcript
                md_lines.append(transcript)
                md_lines.append("")
        
        return "\n".join(md_lines)
    
    @staticmethod
    def _format_timestamp(seconds: float) -> str:
        """Format seconds to HH:MM:SS"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes:02d}:{secs:02d}"
