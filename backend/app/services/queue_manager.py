"""Task queue manager"""
import asyncio
from typing import Dict, Optional, Callable
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class QueueManager:
    """Manage video processing queue"""
    
    def __init__(self, max_concurrent: int = 1):
        """
        Initialize queue manager
        
        Args:
            max_concurrent: Maximum number of concurrent tasks
        """
        self.queue = asyncio.Queue()
        self.processing: Dict[int, Dict] = {}  # task_id -> task info
        self.completed: Dict[int, Dict] = {}  # task_id -> result
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self._task_counter = 0
        self._workers = []
        self._running = False
    
    def start_workers(self, num_workers: int = 1):
        """Start worker tasks"""
        if self._running:
            return
        
        self._running = True
        for i in range(num_workers):
            worker = asyncio.create_task(self._worker(f"worker-{i}"))
            self._workers.append(worker)
        logger.info(f"Started {num_workers} queue workers")
    
    def stop_workers(self):
        """Stop worker tasks"""
        self._running = False
        for worker in self._workers:
            worker.cancel()
        self._workers.clear()
        logger.info("Stopped queue workers")
    
    async def _worker(self, name: str):
        """Worker task that processes queue items"""
        while self._running:
            try:
                task = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                async with self.semaphore:
                    await self._process_task(task)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Worker {name} error: {e}")
    
    async def _process_task(self, task: Dict):
        """Process a single task"""
        task_id = task['id']
        try:
            self.processing[task_id] = task
            logger.info(f"Processing task {task_id}")
            
            # Call the processor function
            processor = task.get('processor')
            if processor:
                await processor(task)
            
            # Mark as completed
            self.completed[task_id] = task
            if task_id in self.processing:
                del self.processing[task_id]
                
        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}")
            task['error'] = str(e)
            task['status'] = 'failed'
            self.completed[task_id] = task
            if task_id in self.processing:
                del self.processing[task_id]
    
    async def add_task(
        self,
        processor: Callable,
        task_data: Dict,
        priority: int = 0
    ) -> int:
        """
        Add task to queue
        
        Args:
            processor: Async function to process the task
            task_data: Task data dict
            priority: Task priority (higher = processed first)
            
        Returns:
            Task ID
        """
        self._task_counter += 1
        task_id = self._task_counter
        
        task = {
            'id': task_id,
            'processor': processor,
            'priority': priority,
            'status': 'pending',
            'created_at': datetime.now(),
            **task_data
        }
        
        await self.queue.put(task)
        logger.info(f"Added task {task_id} to queue")
        return task_id
    
    def get_queue_status(self) -> Dict:
        """Get current queue status"""
        return {
            'queue_size': self.queue.qsize(),
            'processing': len(self.processing),
            'processing_tasks': list(self.processing.values()),
            'completed': len(self.completed),
        }
    
    def get_task_status(self, task_id: int) -> Optional[Dict]:
        """Get status of a specific task"""
        if task_id in self.processing:
            return self.processing[task_id]
        elif task_id in self.completed:
            return self.completed[task_id]
        return None
