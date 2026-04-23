"""
Data Export & Backup
Handles data export, scheduled backups, and disaster recovery.
"""
import json
import logging
import os
import shutil
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from pathlib import Path
from enum import Enum


class ExportFormat(Enum):
    """Supported export formats."""
    JSON = "json"
    CSV = "csv"
    PARQUET = "parquet"
    SQL = "sql"


class BackupSchedule(Enum):
    """Backup frequency."""
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


@dataclass
class BackupConfig:
    """Backup configuration."""
    source_paths: List[str]
    destination: str
    schedule: BackupSchedule
    retention_days: int = 30
    compress: bool = True
    encrypt: bool = False
    exclude_patterns: List[str] = field(default_factory=list)


class DataExporter:
    """
    Data export and backup system.
    Handles multiple export formats and scheduled backups.
    """
    
    def __init__(self, backup_dir: str = "backups"):
        self.logger = logging.getLogger(__name__)
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(exist_ok=True)
        
        # Export handlers
        self.exporters: Dict[ExportFormat, Callable] = {
            ExportFormat.JSON: self._export_json,
            ExportFormat.CSV: self._export_csv,
        }
        
        # Backup history
        self.backups: List[Dict] = []
        
        self.logger.info(f"DataExporter initialized (dir={backup_dir})")
    
    def export_data(self,
                   data: List[Dict],
                   filepath: str,
                   format: ExportFormat = ExportFormat.JSON) -> bool:
        """
        Export data to file.
        
        Args:
            data: Data to export
            filepath: Output path
            format: Export format
            
        Returns:
            True if successful
        """
        try:
            handler = self.exporters.get(format)
            if handler:
                handler(data, filepath)
            else:
                self._export_json(data, filepath)
            
            self.logger.info(f"Exported {len(data)} records to {filepath}")
            return True
            
        except Exception as e:
            self.logger.error(f"Export failed: {e}")
            return False
    
    def _export_json(self, data: List[Dict], filepath: str):
        """Export to JSON."""
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def _export_csv(self, data: List[Dict], filepath: str):
        """Export to CSV."""
        if not data:
            return
        
        import csv
        keys = data[0].keys()
        
        with open(filepath, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(data)
    
    def create_backup(self,
                     sources: List[str],
                     label: str = "") -> Optional[str]:
        """
        Create manual backup.
        
        Args:
            sources: Paths to backup
            label: Backup label
            
        Returns:
            Backup path or None
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f"backup_{label}_{timestamp}" if label else f"backup_{timestamp}"
        backup_path = self.backup_dir / backup_name
        
        try:
            backup_path.mkdir(exist_ok=True)
            
            for source in sources:
                src = Path(source)
                if src.exists():
                    if src.is_dir():
                        shutil.copytree(src, backup_path / src.name, dirs_exist_ok=True)
                    else:
                        shutil.copy2(src, backup_path / src.name)
            
            # Record backup
            backup_info = {
                'id': backup_name,
                'path': str(backup_path),
                'created_at': datetime.now().isoformat(),
                'sources': sources,
                'size_mb': self._get_dir_size(backup_path),
            }
            self.backups.append(backup_info)
            
            self.logger.info(f"Backup created: {backup_path}")
            return str(backup_path)
            
        except Exception as e:
            self.logger.error(f"Backup failed: {e}")
            return None
    
    def _get_dir_size(self, path: Path) -> float:
        """Get directory size in MB."""
        total = 0
        for entry in path.rglob('*'):
            if entry.is_file():
                total += entry.stat().st_size
        return total / (1024 * 1024)
    
    def cleanup_old_backups(self, retention_days: int = 30):
        """
        Remove backups older than retention period.
        
        Args:
            retention_days: Keep backups within this period
        """
        cutoff = datetime.now() - timedelta(days=retention_days)
        removed = 0
        
        for backup in self.backups[:]:
            created = datetime.fromisoformat(backup['created_at'])
            if created < cutoff:
                backup_path = Path(backup['path'])
                if backup_path.exists():
                    shutil.rmtree(backup_path)
                self.backups.remove(backup)
                removed += 1
        
        self.logger.info(f"Cleaned up {removed} old backups")
    
    def list_backups(self) -> List[Dict]:
        """List all backups."""
        return sorted(self.backups, key=lambda x: x['created_at'], reverse=True)
    
    def restore_backup(self, backup_id: str, restore_to: str) -> bool:
        """
        Restore from backup.
        
        Args:
            backup_id: Backup to restore
            restore_to: Destination path
            
        Returns:
            True if successful
        """
        backup = next((b for b in self.backups if b['id'] == backup_id), None)
        if not backup:
            self.logger.error(f"Backup not found: {backup_id}")
            return False
        
        try:
            backup_path = Path(backup['path'])
            restore_path = Path(restore_to)
            
            if restore_path.exists():
                shutil.rmtree(restore_path)
            
            shutil.copytree(backup_path, restore_path)
            
            self.logger.info(f"Restored backup to {restore_to}")
            return True
            
        except Exception as e:
            self.logger.error(f"Restore failed: {e}")
            return False
    
    def get_export_stats(self) -> Dict:
        """Get export statistics."""
        return {
            'backup_dir': str(self.backup_dir),
            'total_backups': len(self.backups),
            'total_size_mb': sum(b.get('size_mb', 0) for b in self.backups),
            'last_backup': self.backups[-1]['created_at'] if self.backups else None,
        }


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)
    
    exporter = DataExporter()
    
    # Sample data
    data = [
        {'id': 1, 'symbol': 'BTCUSDT', 'price': 45000, 'time': '2024-01-01'},
        {'id': 2, 'symbol': 'ETHUSDT', 'price': 3200, 'time': '2024-01-01'},
    ]
    
    # Export
    exporter.export_data(data, "trades.json", ExportFormat.JSON)
    exporter.export_data(data, "trades.csv", ExportFormat.CSV)
    
    # Backup
    backup_path = exporter.create_backup(
        sources=["state/tasks.json", "outbox/"],
        label="daily"
    )
    
    print(f"\nExport & Backup Demo")
    print("=" * 50)
    print(f"Backup: {backup_path}")
    print(f"Stats: {exporter.get_export_stats()}")
    print(f"Backups: {len(exporter.list_backups())}")
