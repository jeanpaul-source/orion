
# Set up logging
logger = logging.getLogger(__name__)

"""
Pipeline monitoring and metrics for ORION ingestion

Tracks performance metrics:
- Duration and throughput (PDFs/sec)
- Acceptance vs. rejection rates
- Chunking statistics (avg chunks/doc, tokens/chunk)
- Quality gate pass/fail breakdown

Created: 2025-11-09 (Phase 5A)
"""

import time
from dataclasses import dataclass, field
from typing import List, Dict
from datetime import datetime
import logging


@dataclass
class PipelineMetrics:
    """Performance metrics for ingestion pipeline"""
    start_time: float
    end_time: float = 0.0
    pdfs_processed: int = 0
    pdfs_accepted: int = 0
    pdfs_rejected: int = 0
    total_chunks: int = 0
    total_tokens: int = 0
    rejection_reasons: Dict[str, int] = field(default_factory=dict)
    
    @property
    def duration_seconds(self) -> float:
        """Total execution time"""
        if self.end_time == 0:
            return time.time() - self.start_time
        return self.end_time - self.start_time
    
    @property
    def pdfs_per_second(self) -> float:
        """Processing throughput"""
        duration = self.duration_seconds
        return self.pdfs_processed / duration if duration > 0 else 0
    
    @property
    def acceptance_rate(self) -> float:
        """Percentage of PDFs that passed quality gates"""
        return self.pdfs_accepted / self.pdfs_processed if self.pdfs_processed > 0 else 0
    
    @property
    def avg_chunks_per_doc(self) -> float:
        """Average number of chunks per accepted document"""
        return self.total_chunks / self.pdfs_accepted if self.pdfs_accepted > 0 else 0
    
    @property
    def avg_tokens_per_chunk(self) -> float:
        """Average tokens in each chunk"""
        return self.total_tokens / self.total_chunks if self.total_chunks > 0 else 0
    
    def add_rejection(self, reason: str) -> None:
        """Track rejection reason"""
        if reason not in self.rejection_reasons:
            self.rejection_reasons[reason] = 0
        self.rejection_reasons[reason] += 1

    def report(self) -> None:
        """Print comprehensive metrics report"""
        logger.info("\n" + "="*70)
        logger.info("PIPELINE PERFORMANCE METRICS")
        logger.info("="*70)
        logger.info(f"Start time:     {datetime.fromtimestamp(self.start_time).isoformat()}")
        logger.info(f"Duration:       {self.duration_seconds:.1f}s")
        logger.info(f"Throughput:     {self.pdfs_per_second:.2f} PDFs/sec")
        logger.info()
        logger.info(f"Processed:      {self.pdfs_processed}")
        logger.info(f"Accepted:       {self.pdfs_accepted} ({self.acceptance_rate:.1%})")
        logger.info(f"Rejected:       {self.pdfs_rejected}")
        logger.info()
        logger.info(f"Total chunks:   {self.total_chunks}")
        logger.info(f"Avg chunks:     {self.avg_chunks_per_doc:.1f} per document")
        
        if self.total_tokens > 0:
            logger.info(f"Total tokens:   {self.total_tokens:,}")
            logger.info(f"Avg tokens:     {self.avg_tokens_per_chunk:.0f} per chunk")
        
        if self.rejection_reasons:
            logger.info()
            logger.info("REJECTION BREAKDOWN:")
            for reason, count in sorted(self.rejection_reasons.items(), 
                                       key=lambda x: x[1], reverse=True):
                percentage = count / self.pdfs_rejected * 100 if self.pdfs_rejected > 0 else 0
                logger.info(f"  • {reason}: {count} ({percentage:.1f}%)")
        
        logger.info("="*70)
    
    def summary_line(self) -> str:
        """One-line summary for logs"""
        return (f"Processed={self.pdfs_processed} | "
                f"Accepted={self.pdfs_accepted} ({self.acceptance_rate:.1%}) | "
                f"AvgChunks={self.avg_chunks_per_doc:.1f} | "
                f"Throughput={self.pdfs_per_second:.2f} PDFs/sec | "
                f"Duration={self.duration_seconds:.1f}s")


def create_metrics() -> PipelineMetrics:
    """Initialize metrics tracker"""
    return PipelineMetrics(start_time=time.time())


if __name__ == "__main__":
    # Example usage
    metrics = create_metrics()
    
    # Simulate processing
    metrics.pdfs_processed = 100
    metrics.pdfs_accepted = 92
    metrics.pdfs_rejected = 8
    metrics.total_chunks = 4232
    metrics.total_tokens = 2_165_000
    
    metrics.add_rejection("Low density: 0.42 (min 0.55)")
    metrics.add_rejection("Low density: 0.51 (min 0.55)")
    metrics.add_rejection("Low density: 0.48 (min 0.55)")
    metrics.add_rejection("Duplicate content")
    metrics.add_rejection("Duplicate content")
    metrics.add_rejection("No text content")
    metrics.add_rejection("Processing error: Corrupt PDF")
    metrics.add_rejection("Processing error: Encrypted")
    
    metrics.end_time = time.time()
    
    logger.info("\nExample metrics report:")
    metrics.report()
    logger.info("\nOne-line summary:")
    logger.info(metrics.summary_line())
