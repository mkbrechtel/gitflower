# Repository Management

CodeFlow provides simple and secure local Git repository management through command-line tools.

## Overview

All repositories are stored in a single directory (`reposDirectory`) with strict naming conventions:
- Repository names must follow slug format: `[a-z0-9-.]` only
- Repositories must end with `.git`
- Organization folders must not end with `.git`
- Names cannot start with `.` or contain `..`

## Configuration

### Setting the Repository Directory

By default, repositories are stored in `./repos/`. You can change this:

```bash
# View current repository directory
codeflow config reposDirectory

# Set a new repository directory
codeflow config reposDirectory ~/my-git-repos
```

## Creating Repositories

Use the `create` command to initialize new bare repositories:

```bash
# Create a simple repository
codeflow create my-project.git

# Create repository in an organization folder
codeflow create work/backend-api.git
codeflow create personal/dotfiles.git
```

### Naming Rules

Valid repository names:
- `my-project.git`
- `backend-api.git`
- `config-files.git`
- `v1.2.3.git`

Invalid names (will be rejected):
- `.hidden.git` (starts with dot)
- `My-Project.git` (contains uppercase)
- `test..repo.git` (contains double dots)
- `project_name.git` (contains underscore)
- `project` (missing .git extension)

## Listing Repositories

The `list` command shows all repositories with metadata:

```bash
codeflow list
```

Output includes:
- Repository path (relative to reposDirectory)
- Size on disk
- Last update time
- Number of branches
- Number of merge requests (if any)
- Warnings for invalid directory names

Example output:
```
Repositories in ./my-repos:

test-project.git
  Size: 1.2 KB
  Last update: 2 minutes ago
  Branches: 1

work/backend-api.git
  Size: 0 B
  Last update: just now
  Branches: 0

personal/dotfiles.git
  Size: 0 B
  Last update: just now
  Branches: 0
```

## Repository Structure

You can organize repositories using subdirectories:

```
my-repos/
├── personal/
│   ├── dotfiles.git/
│   └── notes.git/
├── work/
│   ├── backend-api.git/
│   ├── frontend-app.git/
│   └── shared-libs.git/
├── open-source/
│   └── my-contribution.git/
└── archived/
    └── old-project.git/
```

## Security

- Repository access is controlled by filesystem permissions
- No write operations via web interface
- All repository names are validated to prevent directory traversal
- Special directory names (`.`, `..`) are rejected

## Integration with Git

Created repositories are standard Git bare repositories. You can clone and work with them normally:

```bash
# Clone a local repository
git clone ~/my-repos/test-project.git

# Add as remote to existing repository
git remote add origin ~/my-repos/work/backend-api.git
```

## Troubleshooting

### "Invalid directory name" warnings

If you see warnings about invalid directory names when listing repositories, it means you have directories that don't follow CodeFlow's naming conventions. These directories are ignored but you should rename or remove them.

### Repository not showing up

Ensure the repository:
1. Is in the configured `reposDirectory`
2. Has a name ending with `.git`
3. Follows the slug naming convention
4. Is a valid Git bare repository

### Permission errors

Check that:
1. You have read/write permissions to the `reposDirectory`
2. The repository directories have appropriate permissions (755 for directories, 644 for files)