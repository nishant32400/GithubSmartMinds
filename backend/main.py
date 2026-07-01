"""CLI for the LLM-powered GitHub talent-hunt agent."""
import argparse
import json
import logging

from agent import TalentHuntAgent
from config import config
from scrapers.github_scraper import GitHubError


def parse_args():
    parser = argparse.ArgumentParser(description='Find top GitHub candidates for a job query.')
    parser.add_argument('--query', '-q', required=True,
                        help='Job requirement keywords, e.g. "python backend django"')
    parser.add_argument('--location', '-l', default='', help='Optional preferred location')
    parser.add_argument('--max-results', '-n', type=int, default=10,
                        help='Number of top candidates to return')
    parser.add_argument('--search-size', '-s', type=int, default=100,
                        help='How many GitHub users to scan')
    parser.add_argument('--out', '-o', default='results.json', help='Output JSON file')
    return parser.parse_args()


def main():
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    args = parse_args()
    max_results = config.clamp_max_results(args.max_results, default=10)
    search_size = config.clamp_search_size(args.search_size, default=100)

    agent = TalentHuntAgent()
    print(f"Searching GitHub for: {args.query} (scanning up to {search_size} users)")
    print(f"LLM: {'enabled - ' + (agent.llm.model_name or '') if agent.llm.is_available() else 'disabled (heuristic mode)'}")

    try:
        result = agent.hunt(
            requirements=args.query,
            location=args.location,
            search_size=search_size,
            top_n=max_results,
        )
    except GitHubError as exc:
        print(f"GitHub error: {exc}")
        return 1

    plan = result['plan']
    print(f"Search plan ({plan['source']}): {plan['github_query']}")
    print(f"Scanned {result['scanned']} profiles; top {result['count']} candidates:\n")
    for r in result['candidates']:
        skills = ', '.join((r.get('matched_skills') or r.get('skills', []))[:5])
        print(f"- {r['username']} ({r.get('name') or 'n/a'}) score={r['score']} "
              f"[{r.get('evaluated_by')}] skills={skills}")
        if r.get('fit_summary'):
            print(f"    {r['fit_summary']}")

    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2)
    print(f"\nResults saved to {args.out}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
