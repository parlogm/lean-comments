# Code comments
Default to no comment. Add one only where a reader would otherwise get the code wrong, and make it one sentence. If the reason needs a paragraph, it goes in the commit message or PR description, not the code.
- Never in comments: restating or narrating code, section banners, the change you just made, history ("previously", "no longer", "is now"), ticket chains, design debates, or background from the task prompt. A ticket ID appears only as `TODO(ABC-123)`.
- Javadoc and docstrings only where a linter requires them: one line, no `<p>` paragraphs. Test names say what a test proves, so tests get no Javadoc.
- Don't match the comment density of surrounding code that is already over-commented.
- The `lean-comments` skill has the details and a cleanup pass.
