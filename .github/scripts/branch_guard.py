"""Chaque branche ne touche que son projet : une branche « optimizer » ne peut pas modifier le launcher, etc.

Utilisé par GitHub (à chaque push et pull request) et en local par le hook .githooks/pre-commit.
  python .github/scripts/branch_guard.py --staged        → vérifie ce qu'on s'apprête à committer
  python .github/scripts/branch_guard.py <base>          → vérifie tout ce qui diffère de <base> (ex. origin/main)
Les sous-branches suivent leur parent : « optimizer/graphes » a les droits de « optimizer »."""
import os
import subprocess
import sys

# branche → dossiers et fichiers qu'elle a le droit de modifier
ALLOWED = {
    'launcher': ['apps/launcher/', 'docs/roadmaps/launcher.md'],
    'lights': ['apps/lights/', 'docs/roadmaps/lights.md'],
    'optimizer': ['apps/optimizer/', 'docs/roadmaps/optimizer.md'],
    'ai': ['apps/ai/', 'docs/roadmaps/ai.md'],
    # le socle commun : code partagé, DA, docs, outillage du dépôt
    'shared': ['core/', 'design/', 'docs/', '.github/', '.githooks/', 'README.md', 'CLAUDE.md', '.gitignore', 'LICENSE'],
}


def git(*args):
    return subprocess.run(['git', *args], capture_output=True, text=True, check=True).stdout


def main():
    branch = os.environ.get('GITHUB_HEAD_REF') or os.environ.get('GITHUB_REF_NAME') or \
        git('rev-parse', '--abbrev-ref', 'HEAD').strip()
    project = branch.split('/', 1)[0]
    if project == 'main':
        # sur main on n'arrive que par fusion d'une branche déjà vérifiée ; un commit direct est refusé en local
        if sys.argv[1:] == ['--staged']:
            sys.exit("Pas de commit direct sur main : travaille sur la branche du projet (launcher, lights, "
                     "optimizer, ai ou shared) puis fusionne.")
        return
    if project not in ALLOWED:
        sys.exit(f"Branche « {branch} » inconnue : elle doit commencer par {', '.join(ALLOWED)}.")
    if sys.argv[1:] == ['--staged']:
        files = git('diff', '--cached', '--name-only').split()
    else:
        files = git('diff', '--name-only', f'{sys.argv[1]}...HEAD').split()
    bad = [f for f in files if not any(f == p or f.startswith(p) for p in ALLOWED[project])]
    if bad:
        sys.exit(f"La branche « {branch} » ne doit modifier que {', '.join(ALLOWED[project])}.\n"
                 "Fichiers hors de son projet :\n  " + '\n  '.join(bad) +
                 "\nUn changement du socle commun (core/, design/…) se fait sur la branche « shared ».")
    print(f'branche « {branch} » : {len(files)} fichier(s), tous dans son projet.')


if __name__ == '__main__':
    main()
