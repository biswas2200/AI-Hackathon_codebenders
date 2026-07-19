"""
Analysis Engine Module for DiscoveryOS

Scores and ranks insights based on:
- Frequency metrics
- Business impact assessment
- Customer sentiment
- Source diversity
"""

from typing import List, Dict, Any
from collections import defaultdict


class AnalysisEngine:
    """Analyzes and ranks insights by priority and business impact."""

    def __init__(self):
        """Initialize the analysis engine."""
        self.scored_insights = []

    def score_insights(self, pain_points: List[Dict[str, Any]], 
                      documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Score pain points based on multiple factors.
        Returns ranked list of scored insights.
        """
        scored = []
        
        for pain_point in pain_points:
            score = self._calculate_insight_score(pain_point, documents)
            business_impact = self._assess_business_impact(pain_point, documents)
            
            scored_insight = {
                **pain_point,
                'priority_score': score['priority_score'],
                'frequency_score': score['frequency_score'],
                'impact_score': score['impact_score'],
                'sentiment_score': score['sentiment_score'],
                'business_impact': business_impact,
                'priority_rank': 'pending'  # Will be assigned after sorting
            }
            
            scored.append(scored_insight)
        
        # Sort by priority score
        scored = sorted(scored, key=lambda x: x['priority_score'], reverse=True)
        
        # Assign priority ranks
        for idx, insight in enumerate(scored, 1):
            if idx <= 3:
                insight['priority_rank'] = 'P0 - Critical'
            elif idx <= 7:
                insight['priority_rank'] = 'P1 - High'
            else:
                insight['priority_rank'] = 'P2 - Medium'
        
        self.scored_insights = scored
        return scored

    def _calculate_insight_score(self, pain_point: Dict[str, Any], 
                                 documents: List[Dict[str, Any]]) -> Dict[str, float]:
        """Calculate composite insight score from multiple metrics."""
        
        # Frequency score (0-40 points)
        max_frequency = 10
        frequency_score = min((pain_point['frequency'] / max_frequency) * 40, 40)
        
        # Impact score based on severity (0-30 points)
        severity_map = {'critical': 30, 'high': 20, 'medium': 10}
        impact_score = severity_map.get(pain_point['severity'], 10)
        
        # Sentiment score - negative sentiment increases priority (0-20 points)
        sentiment_score = self._calculate_sentiment_boost(pain_point, documents)
        
        # Source diversity score (0-10 points)
        source_count = pain_point['source_count']
        source_score = min((source_count / len(documents)) * 10, 10)
        
        total_score = frequency_score + impact_score + sentiment_score + source_score
        
        return {
            'priority_score': total_score,
            'frequency_score': frequency_score,
            'impact_score': impact_score,
            'sentiment_score': sentiment_score
        }

    def _calculate_sentiment_boost(self, pain_point: Dict[str, Any], 
                                   documents: List[Dict[str, Any]]) -> float:
        """Calculate sentiment boost from associated documents."""
        doc_sentiments = []
        
        for doc_id in pain_point['document_ids']:
            doc = next((d for d in documents if d['id'] == doc_id), None)
            if doc:
                sentiment = doc.get('sentiment', 'neutral').lower()
                if sentiment == 'negative':
                    doc_sentiments.append(1)
                elif sentiment == 'positive':
                    doc_sentiments.append(-0.5)
                else:
                    doc_sentiments.append(0)
        
        if doc_sentiments:
            avg_sentiment = sum(doc_sentiments) / len(doc_sentiments)
            return max(0, avg_sentiment * 20)
        
        return 0

    def _assess_business_impact(self, pain_point: Dict[str, Any], 
                               documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Assess the business impact of a pain point."""
        
        # Count affected user segments
        affected_segments = set()
        for doc_id in pain_point['document_ids']:
            doc = next((d for d in documents if d['id'] == doc_id), None)
            if doc and doc.get('user_type'):
                affected_segments.add(doc['user_type'])
        
        # Determine impact level
        impact_level = 'medium'
        if pain_point['frequency'] >= 4:
            impact_level = 'critical'
        elif pain_point['frequency'] >= 2 or len(affected_segments) >= 2:
            impact_level = 'high'
        
        return {
            'level': impact_level,
            'affected_user_segments': list(affected_segments),
            'num_affected_segments': len(affected_segments),
            'revenue_risk': self._estimate_revenue_risk(pain_point, impact_level),
            'urgency': self._estimate_urgency(pain_point)
        }

    def _estimate_revenue_risk(self, pain_point: Dict[str, Any], impact_level: str) -> str:
        """Estimate potential revenue impact."""
        risk_map = {
            'critical': 'High - Churn risk, feature barrier',
            'high': 'Medium - User dissatisfaction, competitive risk',
            'medium': 'Low - Quality of life improvement'
        }
        return risk_map.get(impact_level, 'Low')

    def _estimate_urgency(self, pain_point: Dict[str, Any]) -> str:
        """Estimate urgency of addressing the pain point."""
        if pain_point['frequency'] >= 5:
            return 'Immediate (This sprint)'
        elif pain_point['frequency'] >= 3:
            return 'Soon (Next sprint/cycle)'
        else:
            return 'Planned (Next quarter)'

    def rank_by_priority(self) -> List[Dict[str, Any]]:
        """Return insights ranked by priority."""
        return sorted(self.scored_insights, key=lambda x: x['priority_score'], reverse=True)

    def get_top_insights(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top N insights by priority score."""
        return self.rank_by_priority()[:limit]

    def group_by_theme(self, patterns: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Group insights by theme for thematic analysis."""
        themed = {}
        
        for pattern in patterns:
            theme = pattern['theme']
            themed[theme] = {
                'theme': theme,
                'pain_point_count': pattern['pain_point_count'],
                'total_frequency': pattern['total_frequency'],
                'affected_sources': pattern['affected_sources'],
                'priority': 'P0' if pattern['total_frequency'] >= 10 
                          else 'P1' if pattern['total_frequency'] >= 5
                          else 'P2'
            }
        
        return dict(sorted(themed.items(), 
                          key=lambda x: x[1]['total_frequency'], 
                          reverse=True))

    def generate_summary_stats(self, insights: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate summary statistics for all insights."""
        if not insights:
            return {
                'total_insights': 0,
                'average_priority_score': 0,
                'critical_count': 0,
                'high_count': 0,
                'medium_count': 0
            }
        
        priority_counts = defaultdict(int)
        total_score = 0
        
        for insight in insights:
            priority_counts[insight.get('priority_rank', 'P2 - Medium')] += 1
            total_score += insight.get('priority_score', 0)
        
        return {
            'total_insights': len(insights),
            'average_priority_score': total_score / len(insights) if insights else 0,
            'critical_count': priority_counts.get('P0 - Critical', 0),
            'high_count': priority_counts.get('P1 - High', 0),
            'medium_count': priority_counts.get('P2 - Medium', 0),
            'distribution': dict(priority_counts)
        }
