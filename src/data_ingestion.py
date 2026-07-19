"""
Data Ingestion Module for DiscoveryOS

Loads and normalizes customer research data from multiple sources:
- Interview transcripts
- Survey responses
- Support tickets
- Notes and documents

Supports formats: JSON, CSV, TXT
"""

import json
import csv
import os
from typing import List, Dict, Any
from pathlib import Path
from datetime import datetime


class DataIngestionEngine:
    """Loads, parses, and normalizes customer research data from multiple formats."""

    def __init__(self):
        """Initialize the data ingestion engine."""
        self.documents = []
        self.document_index = {}

    def ingest_json(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Load JSON research data.
        Expected format: list of objects with 'content', 'source', 'date' fields.
        """
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        if not isinstance(data, list):
            data = [data]
        
        for item in data:
            normalized = self._normalize_document(item, 'json')
            self.documents.append(normalized)
        
        return data

    def ingest_csv(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Load CSV research data.
        Expected columns: content, source, date (and optional: user_type, sentiment)
        """
        data = []
        with open(file_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                data.append(row)
                normalized = self._normalize_document(row, 'csv')
                self.documents.append(normalized)
        
        return data

    def ingest_txt(self, file_path: str) -> Dict[str, Any]:
        """
        Load plain text research data.
        Treats entire file as single document.
        """
        with open(file_path, 'r') as f:
            content = f.read()
        
        doc = {
            'content': content,
            'source': Path(file_path).name,
            'date': datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat(),
            'format': 'txt'
        }
        normalized = self._normalize_document(doc, 'txt')
        self.documents.append(normalized)
        
        return doc

    def ingest_directory(self, directory_path: str) -> Dict[str, int]:
        """
        Load all supported files from a directory.
        Returns count of documents ingested by format.
        """
        counts = {'json': 0, 'csv': 0, 'txt': 0}
        
        for file_path in Path(directory_path).rglob('*'):
            if file_path.is_file():
                if file_path.suffix == '.json':
                    self.ingest_json(str(file_path))
                    counts['json'] += 1
                elif file_path.suffix == '.csv':
                    self.ingest_csv(str(file_path))
                    counts['csv'] += 1
                elif file_path.suffix == '.txt':
                    self.ingest_txt(str(file_path))
                    counts['txt'] += 1
        
        return counts

    def _normalize_document(self, doc: Dict[str, Any], source_format: str) -> Dict[str, Any]:
        """
        Normalize document to standard internal format.
        Standard fields: id, content, source, date, format, user_type, sentiment
        """
        doc_id = len(self.documents)
        
        normalized = {
            'id': doc_id,
            'content': doc.get('content', ''),
            'source': doc.get('source', 'unknown'),
            'date': doc.get('date', datetime.now().isoformat()),
            'format': source_format,
            'user_type': doc.get('user_type', 'general'),
            'sentiment': doc.get('sentiment', 'neutral')
        }
        
        self.document_index[doc_id] = normalized
        return normalized

    def get_documents(self) -> List[Dict[str, Any]]:
        """Return all ingested documents."""
        return self.documents

    def get_document_by_id(self, doc_id: int) -> Dict[str, Any]:
        """Retrieve a specific document by ID."""
        return self.document_index.get(doc_id)

    def get_statistics(self) -> Dict[str, Any]:
        """Return ingestion statistics."""
        formats = {}
        user_types = {}
        sentiments = {}
        
        for doc in self.documents:
            formats[doc['format']] = formats.get(doc['format'], 0) + 1
            user_types[doc['user_type']] = user_types.get(doc['user_type'], 0) + 1
            sentiments[doc['sentiment']] = sentiments.get(doc['sentiment'], 0) + 1
        
        return {
            'total_documents': len(self.documents),
            'by_format': formats,
            'by_user_type': user_types,
            'by_sentiment': sentiments
        }
