"""
Insight Extraction Module for DiscoveryOS

Extracts pain points, patterns, and segments from customer research data
using NLP techniques:
- Pain point identification (keyword and semantic analysis)
- Pattern detection across multiple sources
- User segment identification and classification
"""

import re
from typing import List, Dict, Any, Tuple
from collections import Counter, defaultdict


class InsightExtractor:
    """Extracts pain points, patterns, and user segments from customer research."""

    def __init__(self):
        """Initialize the insight extractor with pain point keywords and patterns."""
        self.pain_point_keywords = [
            'difficult', 'frustrat', 'slow', 'confus', 'broken', 'fail', 'problem',
            'issue', 'bug', 'error', 'pain', 'hard', 'struggle', 'annoying', 'waste',
            'time-consum', 'tedious', 'cumbersom', 'complicated', 'manual', 'repeat',
            'missing', 'need', 'want', 'should have', 'wish', 'expect', 'require',
            'difficult', 'unwieldy', 'clunky', 'buggy', 'unreliable', 'slow',
            'expensive', 'costly', 'overpriced', 'limited', 'insufficient'
        ]
        
        self.user_segment_keywords = {
            'enterprise': ['enterprise', 'large team', 'scale', 'compliance', 'security', 'admin'],
            'startup': ['startup', 'early stage', 'growth', 'bootstrap', 'fast', 'agile'],
            'freelancer': ['freelancer', 'solo', 'independent', 'side project', 'personal'],
            'team_small': ['small team', '2-10 people', 'collaborative', 'team of'],
            'team_large': ['large team', '100+', 'thousands', 'distributed'],
            'technical': ['developer', 'engineer', 'technical', 'api', 'code', 'integration'],
            'non_technical': ['non-technical', 'business user', 'executive', 'manager'],
        }
        
        self.extracted_insights = []

    def extract_pain_points(self, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Extract pain points from documents.
        Returns list of pain point objects with: text, severity, frequency, document_ids
        """
        pain_points = defaultdict(lambda: {'ids': [], 'mentions': 0})
        
        for doc in documents:
            content = doc['content'].lower()
            sentences = self._split_sentences(content)
            
            for sentence in sentences:
                if self._contains_pain_indicator(sentence):
                    # Extract pain point text (limit to sentence)
                    pain_text = sentence.strip()
                    
                    # Normalize for deduplication
                    normalized = self._normalize_text(pain_text)
                    
                    pain_points[normalized]['ids'].append(doc['id'])
                    pain_points[normalized]['mentions'] += 1
                    pain_points[normalized]['text'] = pain_text
        
        # Convert to list and add metadata
        result = []
        for normalized, data in pain_points.items():
            severity = self._calculate_severity(data['mentions'], data['ids'])
            
            result.append({
                'text': data['text'],
                'normalized': normalized,
                'frequency': data['mentions'],
                'severity': severity,
                'source_count': len(set(data['ids'])),
                'document_ids': list(set(data['ids']))
            })
        
        self.extracted_insights = result
        return sorted(result, key=lambda x: x['frequency'], reverse=True)

    def extract_patterns(self, pain_points: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Detect patterns across pain points.
        Groups related pain points into themes.
        """
        patterns = {}
        
        theme_map = {
            'performance': ['slow', 'fast', 'speed', 'lag', 'delay', 'timeout', 'responsiv'],
            'usability': ['difficult', 'confus', 'hard', 'unintuitive', 'complex', 'clunky', 'interface'],
            'reliability': ['broken', 'fail', 'crash', 'error', 'bug', 'unstable', 'downtime'],
            'integration': ['integrat', 'api', 'connect', 'sync', 'third-party', 'plugin', 'workflow'],
            'cost': ['expensive', 'costly', 'price', 'overpriced', 'budget', 'afford', 'value'],
            'features': ['missing', 'need', 'want', 'should have', 'lack', 'support', 'capability'],
            'documentation': ['document', 'unclear', 'guide', 'tutorial', 'onboarding', 'learn'],
            'support': ['support', 'help', 'response time', 'customer service', 'ticket', 'resolution'],
            'workflow': ['workflow', 'process', 'automat', 'manual', 'repeat', 'tedious', 'inefficient'],
        }
        
        for pain_point in pain_points:
            text = pain_point['text'].lower()
            
            for theme, keywords in theme_map.items():
                if any(keyword in text for keyword in keywords):
                    if theme not in patterns:
                        patterns[theme] = {
                            'pain_points': [],
                            'total_frequency': 0,
                            'affected_sources': set()
                        }
                    
                    patterns[theme]['pain_points'].append(pain_point)
                    patterns[theme]['total_frequency'] += pain_point['frequency']
                    patterns[theme]['affected_sources'].update(pain_point['document_ids'])
        
        # Convert to list format
        result = []
        for theme, data in patterns.items():
            result.append({
                'theme': theme,
                'pain_point_count': len(data['pain_points']),
                'total_frequency': data['total_frequency'],
                'affected_sources': len(data['affected_sources']),
                'top_pain_points': sorted(
                    data['pain_points'],
                    key=lambda x: x['frequency'],
                    reverse=True
                )[:3]
            })
        
        return sorted(result, key=lambda x: x['total_frequency'], reverse=True)

    def identify_user_segments(self, documents: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """
        Identify user segments from document content.
        Returns segments with: characteristics, pain_points, count
        """
        segments = defaultdict(lambda: {'docs': [], 'pain_points': []})
        
        for doc in documents:
            content = doc['content'].lower()
            
            for segment, keywords in self.user_segment_keywords.items():
                if any(keyword in content for keyword in keywords):
                    segments[segment]['docs'].append(doc['id'])
        
        # Add user_type from document metadata
        for doc in documents:
            user_type = doc.get('user_type', 'general')
            if user_type and user_type != 'general':
                segments[user_type]['docs'].append(doc['id'])
        
        # Build result with segment analysis
        result = {}
        for segment, data in segments.items():
            result[segment] = {
                'count': len(set(data['docs'])),
                'document_ids': list(set(data['docs'])),
                'characteristics': self.user_segment_keywords.get(segment, [])
            }
        
        return dict(sorted(result.items(), key=lambda x: x[1]['count'], reverse=True))

    def _contains_pain_indicator(self, text: str) -> bool:
        """Check if text contains pain point indicators."""
        return any(keyword in text for keyword in self.pain_point_keywords)

    def _calculate_severity(self, frequency: int, doc_ids: List[int]) -> str:
        """Calculate severity based on frequency and source diversity."""
        unique_sources = len(set(doc_ids))
        
        if frequency >= 3 and unique_sources >= 2:
            return 'critical'
        elif frequency >= 2 or unique_sources >= 2:
            return 'high'
        else:
            return 'medium'

    def _normalize_text(self, text: str) -> str:
        """Normalize text for deduplication."""
        text = text.lower()
        text = re.sub(r'[^a-z0-9\s]', '', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences."""
        sentences = re.split(r'[.!?]+', text)
        return [s.strip() for s in sentences if s.strip()]

    def get_all_insights(self) -> List[Dict[str, Any]]:
        """Return all extracted insights."""
        return self.extracted_insights
