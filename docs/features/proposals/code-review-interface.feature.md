# Feature: Code Review Interface

## Overview
Provide a read-only web interface for reviewing code changes, viewing diffs, browsing repository contents, and understanding the impact of proposed changes.

## Goals
- Enable efficient code review without external tools
- Display diffs clearly with syntax highlighting
- Support navigation through large changesets
- Provide context for understanding changes
- Generate Git commands for reviewers

## User Stories

1. As a user, I want to browse repository files at any commit with syntax highlighting and folder navigation
2. As a user, I want to view diffs in inline (default) or side-by-side format with context and file statistics
3. As a user, I want single-file diff view for large files to focus on specific changes
4. As a user, I want raw file view to see unprocessed file contents
5. As a user, I want to inspect commits with full messages, metadata, and changed file lists
6. As a user, I want to navigate efficiently with breadcrumbs, file switching, and direct line linking
7. As a user, I want to copy Git commands for checking out branches, fetching changes, or cherry-picking
8. As a user, I want markdown files rendered properly with image support
9. As an AI agent, I want to access file contents and analyze commit patterns programmatically

## Acceptance Criteria

### File Viewer
- [ ] Syntax highlighting for common languages
- [ ] Line numbers with linkable anchors
- [ ] File tree navigation sidebar
- [ ] Display file size and type
- [ ] Handle large files gracefully
- [ ] Show file at any commit/branch
- [ ] Raw file view option (unprocessed content)

### Diff Display
- [ ] Inline diff view (default)
- [ ] Side-by-side diff view option
- [ ] Toggle between inline and side-by-side
- [ ] Single-file diff view for focused review
- [ ] Syntax highlighting in diffs
- [ ] Expand context lines
- [ ] Show added/removed/modified lines clearly
- [ ] Handle renamed files
- [ ] Display binary file changes appropriately
- [ ] Pagination for large file diffs

### Commit View
- [ ] Full commit message display
- [ ] Author and timestamp
- [ ] Parent commit links
- [ ] List of changed files
- [ ] Jump to file changes
- [ ] Copy commit SHA

### Code Navigation
- [ ] File path breadcrumbs
- [ ] Quick file switcher
- [ ] Line number permalinks
- [ ] Search within file
- [ ] Navigate with keyboard
- [ ] Responsive design

### Performance
- [ ] Syntax highlighting loads quickly
- [ ] Large diffs paginated
- [ ] Progressive enhancement
- [ ] Efficient memory usage

### Markdown Support
- [ ] Render README files
- [ ] Preview markdown changes
- [ ] Support GitHub-flavored markdown
- [ ] Display images inline
