"""
Scheduler - Handles scheduled tasks and cron jobs
"""
import threading
import time
import logging
from datetime import datetime
from typing import Dict, Callable, List, Optional
import uuid
try:
    from croniter import croniter
except ImportError:
    croniter = None

logger = logging.getLogger(__name__)

class Job:
    def __init__(self, name: str, callback: Callable, trigger_time: Optional[datetime] = None, cron_expr: str = None, args: tuple = (), kwargs: dict = None):
        self.id = str(uuid.uuid4())
        self.name = name
        self.callback = callback
        self.trigger_time = trigger_time
        self.cron_expr = cron_expr
        self.args = args or ()
        self.kwargs = kwargs or {}
        self.enabled = True
        
        # For recurring jobs, calculate next run
        if self.cron_expr and croniter:
            if not self.trigger_time:
                self.schedule_next_cron()
    
    def schedule_next_cron(self):
        """Calculate next trigger time based on cron expression"""
        if self.cron_expr and croniter:
            iter = croniter(self.cron_expr, datetime.now())
            self.trigger_time = iter.get_next(datetime)
            logger.debug(f"Scheduled '{self.name}' for {self.trigger_time}")

class Scheduler:
    """
    Central scheduler for one-time and recurring tasks.
    """
    
    def __init__(self):
        self.jobs: List[Job] = []
        self._lock = threading.Lock()
        self._running = False
        self._thread = None
        
        if not croniter:
            logger.warning("croniter not installed. Recurring jobs will not work.")

    def start(self):
        """Start the scheduler worker thread"""
        if self._running:
            return
            
        self._running = True
        self._thread = threading.Thread(target=self._worker_loop, daemon=True, name="SchedulerWorker")
        self._thread.start()
        logger.info("   ⏰ Scheduler started")

    def stop(self):
        """Stop the scheduler"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)

    def schedule_once(self, name: str, run_at: datetime, callback: Callable, args=(), kwargs=None) -> str:
        """Schedule a one-time job"""
        job = Job(name, callback, trigger_time=run_at, args=args, kwargs=kwargs)
        with self._lock:
            self.jobs.append(job)
        return job.id

    def schedule_cron(self, name: str, cron_expr: str, callback: Callable, args=(), kwargs=None) -> str:
        """Schedule a recurring cron job"""
        if not croniter:
            logger.error("Cannot schedule cron job: croniter not installed")
            return None
            
        job = Job(name, callback, cron_expr=cron_expr, args=args, kwargs=kwargs)
        with self._lock:
            self.jobs.append(job)
        return job.id
    
    def cancel(self, job_id: str = None, name: str = None):
        """Cancel a job by ID or Name"""
        with self._lock:
            if job_id:
                self.jobs = [j for j in self.jobs if j.id != job_id]
            elif name:
                self.jobs = [j for j in self.jobs if j.name != name]

    def get_jobs(self) -> List[Dict]:
        """Get list of active jobs"""
        with self._lock:
            return [{
                "id": j.id,
                "name": j.name,
                "trigger_time": j.trigger_time.isoformat() if j.trigger_time else None,
                "recurring": bool(j.cron_expr)
            } for j in self.jobs]

    def _worker_loop(self):
        """Main loop checking for pending jobs"""
        while self._running:
            try:
                now = datetime.now()
                to_run = []
                
                with self._lock:
                    # Identify jobs to run
                    for job in self.jobs:
                        if job.enabled and job.trigger_time and job.trigger_time <= now:
                            to_run.append(job)
                    
                    # Process running jobs
                    for job in to_run:
                        if job.cron_expr:
                            # Reschedule recurring
                            job.schedule_next_cron()
                        else:
                            # Remove one-time
                            self.jobs.remove(job)
                
                # Execute callbacks (outside lock)
                for job in to_run:
                    try:
                        job.callback(*job.args, **job.kwargs)
                    except Exception as e:
                        logger.error(f"Job '{job.name}' failed: {e}")
                
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
            
            time.sleep(1.0)
