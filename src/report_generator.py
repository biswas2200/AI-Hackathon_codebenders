"""
Report Generator Module for DiscoveryOS

Generates comprehensive, traceable reports in multiple formats:
- JSON structured data
- Markdown readable reports
- Links back to source documents
"""

import json
from typing import List, Dict, Any
from datetime import datetime
from pathlib import Path


class ReportGenerator:
    """Generates prioritized problem space reports in multiple formats."""

    def __init__(self, output_dir: str = 'reports'):
        """Initialize the report generator."""
        self.output_dir = output_dir
        Path(output_dir).mkdir(parents=True, exist_ok=True)

    def generate_report(self, 
                       insights: List[Dict[str, Any]],
                       patterns: List[Dict[str, Any]],
                       segments: Dict[str, Dict[str, Any]],
                       documents: List[Dict[str, Any]],
                       summary_stats: Dict[str, Any]) -> Dict[str, str]:
        """
        Generate complete report in both JSON and Markdown formats.
        Returns dict with file paths: {'json': path, 'markdown': path}
        """
        
        report_data = {
            'metadata': self._generate_metadata(),
            'summary': summary_stats,
            'themes': self._organize_by_theme(patterns, insights),
            'insights': self._prepare_insights_for_report(insights),
            'user_segments': self._prepare_segments_for_report(segments),
            'top_priority_issues': insights[:5],
            'documentation': {
                'total_documents_analyzed': len(documents),
                'documents': self._prepare_documents_for_report(documents)
            }
        }
        
        # Generate JSON report
        json_path = self._save_json_report(report_data)
        
        # Generate Markdown report
        markdown_path = self._save_markdown_report(
            report_data, insights, patterns, segments, documents
        )
        
        return {
            'json': json_path,
            'markdown': markdown_path
        }

    def _generate_metadata(self) -> Dict[str, Any]:
        """Generate report metadata."""
        return {
            'report_name': 'DiscoveryOS - Prioritized Problem Space Report',
            'generated_at': datetime.now().isoformat(),
            'version': '1.0',
            'system': 'DiscoveryOS Product Discovery AI Agent'
        }

    def _organize_by_theme(self, patterns: List[Dict[str, Any]], 
                          insights: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Organize themes with associated pain points."""
        themed = []
        
        for pattern in patterns:
            theme_data = {
                'name': pattern['theme'].replace('_', ' ').title(),
                'pain_point_count': pattern['pain_point_count'],
                'total_frequency': pattern['total_frequency'],
                'affected_sources': pattern['affected_sources'],
                'top_issues': []
            }
            
            # Get top 3 pain points for this theme
            for pp in pattern['top_pain_points']:
                theme_data['top_issues'].append({
                    'text': pp['text'],
                    'frequency': pp['frequency'],
                    'severity': pp['severity']
                })
            
            themed.append(theme_data)
        
        return themed

    def _prepare_insights_for_report(self, insights: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Prepare insights for report output."""
        prepared = []
        
        for idx, insight in enumerate(insights, 1):
            prepared.append({
                'rank': idx,
                'priority': insight.get('priority_rank', 'P2 - Medium'),
                'score': round(insight.get('priority_score', 0), 2),
                'text': insight.get('text', ''),
                'frequency': insight.get('frequency', 0),
                'severity': insight.get('severity', ''),
                'affected_sources': insight.get('source_count', 0),
                'business_impact': insight.get('business_impact', {}),
                'document_ids': insight.get('document_ids', [])
            })
        
        return prepared

    def _prepare_segments_for_report(self, segments: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Prepare user segments for report output."""
        prepared = []
        
        for segment_name, segment_data in segments.items():
            prepared.append({
                'segment': segment_name.replace('_', ' ').title(),
                'representation': segment_data['count'],
                'characteristics': segment_data.get('characteristics', []),
                'document_ids': segment_data.get('document_ids', [])
            })
        
        return prepared

    def _prepare_documents_for_report(self, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Prepare documents reference for report."""
        prepared = []
        
        for doc in documents:
            prepared.append({
                'id': doc['id'],
                'source': doc.get('source', 'unknown'),
                'format': doc.get('format', 'unknown'),
                'date': doc.get('date', 'unknown'),
                'user_type': doc.get('user_type', 'general'),
                'sentiment': doc.get('sentiment', 'neutral'),
                'preview': doc['content'][:200] + '...' if len(doc['content']) > 200 else doc['content']
            })
        
        return prepared

    def _save_json_report(self, report_data: Dict[str, Any]) -> str:
        """Save report as JSON file."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'discovery_report_{timestamp}.json'
        filepath = Path(self.output_dir) / filename
        
        with open(filepath, 'w') as f:
            json.dump(report_data, f, indent=2)
        
        return str(filepath)

    def _save_markdown_report(self, 
                            report_data: Dict[str, Any],
                            insights: List[Dict[str, Any]],
                            patterns: List[Dict[str, Any]],
                            segments: Dict[str, Dict[str, Any]],
                            documents: List[Dict[str, Any]]) -> str:
        """Save report as Markdown file."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'discovery_report_{timestamp}.md'
        filepath = Path(self.output_dir) / filename
        
        md_content = self._build_markdown_content(
            report_data, insights, patterns, segments, documents
        )
        
        with open(filepath, 'w') as f:
            f.write(md_content)
        
        return str(filepath)

    def _build_markdown_content(self, 
                               report_data: Dict[str, Any],
                               insights: List[Dict[str, Any]],
                               patterns: List[Dict[str, Any]],
                               segments: Dict[str, Dict[str, Any]],
                               documents: List[Dict[str, Any]]) -> str:
        """Build complete Markdown report content."""
        
        md = f"""# {report_data['metadata']['report_name']}

**Generated:** {report_data['metadata']['generated_at']}

---

## Executive Summary

This report analyzes customer research data to identify the most critical product issues and opportunities.

### Key Metrics
- **Total Documents Analyzed:** {len(documents)}
- **Total Pain Points Identified:** {report_data['summary']['total_insights']}
- **Critical Issues (P0):** {report_data['summary']['critical_count']}
- **High Priority Issues (P1):** {report_data['summary']['high_count']}
- **Average Priority Score:** {round(report_data['summary']['average_priority_score'], 2)}/100

---

## Top Priority Issues (P0 - Critical)

"""
        
        # Add top priority issues
        for idx, insight in enumerate(insights[:5], 1):
            md += f"""### {idx}. {insight['text']}

- **Priority:** {insight.get('priority_rank', 'P2')}
- **Priority Score:** {round(insight.get('priority_score', 0), 2)}/100
- **Frequency:** Mentioned {insight['frequency']} times
- **Severity:** {insight['severity'].title()}
- **Affected User Groups:** {insight['source_count']} different segments
- **Business Impact:** {insight['business_impact']['level'].title()}
- **Revenue Risk:** {insight['business_impact']['revenue_risk']}
- **Urgency:** {insight['business_impact']['urgency']}
- **Source Documents:** {', '.join([str(i) for i in insight['document_ids'][:3]])}

"""
        
        # Add themes section
        md += f"\n## Problem Space Themes\n\n"
        for pattern in patterns[:7]:
            md += f"""### {pattern['theme'].replace('_', ' ').title()}

- **Pain Points Identified:** {pattern['pain_point_count']}
- **Total Frequency:** {pattern['total_frequency']} mentions
- **Affected Data Sources:** {pattern['affected_sources']}

**Top Issues in this Theme:**
"""
            for pp in pattern['top_pain_points']:
                md += f"- {pp['text']} ({pp['frequency']}x)\n"
            md += "\n"
        
        # Add user segments section
        md += f"\n## User Segments Represented\n\n"
        for segment_name, segment_data in sorted(segments.items(), 
                                                 key=lambda x: x[1]['count'], 
                                                 reverse=True):
            md += f"""### {segment_name.replace('_', ' ').title()}

- **Representation:** {segment_data['count']} documents
- **Characteristics:** {', '.join(segment_data['characteristics'][:3]) if segment_data['characteristics'] else 'General'}

"""
        
        # Add research sources section
        md += f"\n## Research Data Sources\n\n"
        md += f"**Total Documents:** {len(documents)}\n\n"
        
        for doc in documents[:10]:
            md += f"""- **[Doc #{doc['id']}]** {doc['source']}
  - Type: {doc['format'].upper()}
  - Date: {doc['date']}
  - User Type: {doc['user_type']}
  - Sentiment: {doc['sentiment']}
  - Preview: {doc['preview']}

"""
        
        # Add methodology section
        md += f"""
---

## Methodology

### Data Collection
- Customer interviews and transcripts
- Survey responses
- Support tickets and conversations
- User notes and feedback

### Analysis Approach
1. **Data Ingestion:** Parse and normalize research data from multiple formats
2. **Insight Extraction:** Identify pain points using NLP keyword and semantic analysis
3. **Pattern Detection:** Group related pain points into thematic categories
4. **Segment Identification:** Classify users by characteristics and behaviors
5. **Priority Scoring:** Rank issues by frequency, severity, business impact, and sentiment
6. **Report Generation:** Create actionable, traceable findings

### Scoring Methodology
- **Priority Score (0-100):** Composite score based on:
  - Frequency (0-40 points)
  - Severity Level (0-30 points)
  - Sentiment Impact (0-20 points)
  - Source Diversity (0-10 points)

---

## Recommendations

1. **Immediate Action:** Address P0 critical issues in the next sprint
2. **Next Sprint:** Plan solutions for P1 high-priority issues
3. **Roadmap Planning:** Incorporate P2 medium-priority improvements into quarterly goals
4. **User Research:** Conduct follow-up interviews with affected user segments
5. **Monitoring:** Track resolution and gather feedback to validate solutions

---

**Report System:** DiscoveryOS v1.0
**Generated by:** Product Discovery AI Agent
"""
        
        return md

    def save_structured_data(self, insights: List[Dict[str, Any]], 
                            output_file: str = 'structured_insights.json') -> str:
        """Save structured insight data for downstream processing."""
        filepath = Path(self.output_dir) / output_file
        
        structured = {
            'insights': insights,
            'export_date': datetime.now().isoformat()
        }
        
        with open(filepath, 'w') as f:
            json.dump(structured, f, indent=2)
        
        return str(filepath)
