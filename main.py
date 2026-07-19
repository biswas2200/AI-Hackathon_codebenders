"""
DiscoveryOS: Product Discovery & User Research Intelligence AI Agent
Main Entry Point

This application runs the complete pipeline:
1. Data Ingestion - Load customer research from multiple sources
2. Insight Extraction - Extract pain points, patterns, and segments
3. Analysis Engine - Score and rank insights by priority
4. Report Generation - Create prioritized problem space report
"""

import sys
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from data_ingestion import DataIngestionEngine
from insight_extraction import InsightExtractor
from analysis_engine import AnalysisEngine
from report_generator import ReportGenerator


def main():
    """Run the complete DiscoveryOS pipeline."""
    
    print("\n" + "="*70)
    print("DiscoveryOS: Product Discovery & User Research Intelligence")
    print("="*70 + "\n")
    
    # ========================================================================
    # STEP 1: DATA INGESTION
    # ========================================================================
    print("📥 STEP 1: Data Ingestion")
    print("-" * 70)
    
    ingestion = DataIngestionEngine()
    
    # Load sample data
    print("Loading sample research data...")
    ingestion.ingest_json('sample_data/research_data.json')
    ingestion.ingest_json('sample_data/additional_research.json')
    ingestion.ingest_csv('sample_data/feedback.csv')
    
    documents = ingestion.get_documents()
    stats = ingestion.get_statistics()
    
    print(f"✓ Documents loaded: {stats['total_documents']}")
    print(f"  - By format: {stats['by_format']}")
    print(f"  - By user type: {stats['by_user_type']}")
    print(f"  - By sentiment: {stats['by_sentiment']}")
    print()
    
    # ========================================================================
    # STEP 2: INSIGHT EXTRACTION
    # ========================================================================
    print("🔍 STEP 2: Insight Extraction")
    print("-" * 70)
    
    extractor = InsightExtractor()
    
    # Extract pain points
    print("Extracting pain points...")
    pain_points = extractor.extract_pain_points(documents)
    print(f"✓ Pain points identified: {len(pain_points)}")
    print(f"  Top 5 pain points:")
    for idx, pp in enumerate(pain_points[:5], 1):
        print(f"    {idx}. [{pp['severity'].upper()}] {pp['text'][:60]}... (x{pp['frequency']})")
    print()
    
    # Extract patterns
    print("Detecting patterns...")
    patterns = extractor.extract_patterns(pain_points)
    print(f"✓ Themes identified: {len(patterns)}")
    print(f"  Themes: {', '.join([p['theme'] for p in patterns[:5]])}")
    print()
    
    # Identify user segments
    print("Identifying user segments...")
    segments = extractor.identify_user_segments(documents)
    print(f"✓ User segments found: {len(segments)}")
    print(f"  Segments: {', '.join(list(segments.keys())[:5])}")
    print()
    
    # ========================================================================
    # STEP 3: ANALYSIS ENGINE
    # ========================================================================
    print("📊 STEP 3: Insight Analysis & Scoring")
    print("-" * 70)
    
    analyzer = AnalysisEngine()
    
    # Score insights
    print("Scoring and ranking insights...")
    scored_insights = analyzer.score_insights(pain_points, documents)
    print(f"✓ Insights scored: {len(scored_insights)}")
    print()
    
    # Get summary stats
    summary_stats = analyzer.generate_summary_stats(scored_insights)
    print("Summary Statistics:")
    print(f"  - Total insights: {summary_stats['total_insights']}")
    print(f"  - Average priority score: {summary_stats['average_priority_score']:.2f}/100")
    print(f"  - Critical (P0): {summary_stats['critical_count']}")
    print(f"  - High (P1): {summary_stats['high_count']}")
    print(f"  - Medium (P2): {summary_stats['medium_count']}")
    print()
    
    # Display top 5 insights
    print("Top 5 Priority Issues:")
    for idx, insight in enumerate(scored_insights[:5], 1):
        print(f"  {idx}. [{insight['priority_rank']}] Score: {insight['priority_score']:.1f}")
        print(f"     {insight['text'][:70]}...")
        print(f"     Frequency: {insight['frequency']}x | Impact: {insight['business_impact']['level']}")
    print()
    
    # ========================================================================
    # STEP 4: REPORT GENERATION
    # ========================================================================
    print("📄 STEP 4: Report Generation")
    print("-" * 70)
    
    reporter = ReportGenerator('reports')
    
    print("Generating comprehensive reports...")
    report_files = reporter.generate_report(
        scored_insights,
        patterns,
        segments,
        documents,
        summary_stats
    )
    
    print(f"✓ Reports generated successfully!")
    print(f"  - JSON Report: {report_files['json']}")
    print(f"  - Markdown Report: {report_files['markdown']}")
    print()
    
    # ========================================================================
    # FINAL SUMMARY
    # ========================================================================
    print("="*70)
    print("✓ DiscoveryOS Analysis Complete!")
    print("="*70)
    print()
    print("FINDINGS SUMMARY:")
    print(f"  • {stats['total_documents']} customer research documents analyzed")
    print(f"  • {len(pain_points)} unique pain points identified")
    print(f"  • {len(patterns)} problem space themes discovered")
    print(f"  • {len(segments)} user segments represented")
    print()
    print("TOP BUSINESS IMPACT THEMES:")
    for idx, pattern in enumerate(patterns[:3], 1):
        print(f"  {idx}. {pattern['theme'].replace('_', ' ').title()}")
        print(f"     - {pattern['pain_point_count']} pain points | {pattern['total_frequency']} total mentions")
    print()
    print("CRITICAL ISSUES REQUIRING IMMEDIATE ATTENTION:")
    for idx, insight in enumerate(scored_insights[:3], 1):
        print(f"  {idx}. {insight['text'][:60]}...")
        print(f"     Priority: {insight['priority_rank']} | Urgency: {insight['business_impact']['urgency']}")
    print()
    print(f"Reports available in: {Path('reports').absolute()}")
    print()


if __name__ == '__main__':
    main()
