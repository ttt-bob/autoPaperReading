(function initializeSummaryRenderer(global) {
  const metadataFields = new Set([
    '标题',
    '作者列表',
    '作者列表（原文）',
    '所属机构',
    '发表时间',
    '开源代码地址',
    '开源许可证',
    '开源许可证类型',
  ]);

  const breakFields = [
    ...metadataFields,
    '该研究要解决什么问题',
    '目前最好的方法存在哪些不足',
    '为什么这个问题重要',
    '数据集（全称）',
    '数据集规模',
    'Baseline 方法（全称）',
    'Baseline方法（全称）',
    '评估指标',
  ];

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function renderInline(value) {
    return escapeHtml(value)
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*([^*]+?)\*/g, '<em>$1</em>')
      .replace(
        /https?:\/\/[^\s<，。；、）》）\]]+/g,
        url => `<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>`,
      );
  }

  function normalizeText(text) {
    let normalized = String(text).replace(/\r\n?/g, '\n').trim();
    breakFields.forEach(field => {
      const escapedField = field.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      normalized = normalized.replace(
        new RegExp(`([^\\n*-])\\s+(?=${escapedField}[：:])`, 'g'),
        '$1\n',
      );
    });
    return normalized;
  }

  function splitField(value, metadataOnly = false) {
    const match = value.match(/^(.{1,48}?)[：:]\s*(.+)$/);
    if (!match) return null;
    const label = match[1].replace(/\*\*/g, '').trim();
    if (metadataOnly && !metadataFields.has(label)) return null;
    if (!metadataOnly && /[。！？；]/.test(label)) return null;
    return { label, content: match[2].trim() };
  }

  function render(text) {
    if (!text) return '<p>暂无总结</p>';
    const lines = normalizeText(text).split('\n');
    const html = ['<div class="summary-document">'];
    let sectionOpen = false;
    let sectionKind = '';
    let listTag = '';

    const closeList = () => {
      if (!listTag) return;
      html.push(`</${listTag}>`);
      listTag = '';
    };
    const closeSection = () => {
      if (!sectionOpen) return;
      closeList();
      html.push('</div></section>');
      sectionOpen = false;
      sectionKind = '';
    };
    const openList = tag => {
      if (listTag === tag) return;
      closeList();
      listTag = tag;
      html.push(`<${tag} class="summary-list">`);
    };

    lines.forEach(rawLine => {
      const line = rawLine.trim().replace(/\s{2,}$/, '');
      if (!line) {
        closeList();
        return;
      }

      const headingMatch = line.match(/^(#{1,3})\s+(.+)$/);
      if (headingMatch) {
        closeList();
        const level = headingMatch[1].length;
        const heading = headingMatch[2].trim();
        const isNumberedSubheading = level === 2 && /^\d+[.、]\s*/.test(heading) && sectionOpen;

        if (level === 2 && !isNumberedSubheading) {
          closeSection();
          sectionKind = /论文基本信息/.test(heading)
            ? 'metadata'
            : (/一句话总结/.test(heading) ? 'highlight' : '');
          const kindClass = sectionKind ? ` summary-section--${sectionKind}` : '';
          html.push(
            `<section class="summary-section${kindClass}">`,
            `<h2>${renderInline(heading)}</h2>`,
            '<div class="summary-section-body">',
          );
          sectionOpen = true;
          return;
        }

        if (level === 1) {
          closeSection();
          html.push(`<h1>${renderInline(heading)}</h1>`);
          return;
        }

        const insight = heading.match(/^(\d+[.、]\s*)?\*\*(.+?)\*\*[：:]\s*(.+)$/);
        if (insight) {
          html.push(
            '<div class="summary-insight">',
            `<h3>${renderInline(`${insight[1] || ''}${insight[2]}`)}</h3>`,
            `<p>${renderInline(insight[3])}</p>`,
            '</div>',
          );
        } else {
          html.push(`<h3>${renderInline(heading)}</h3>`);
        }
        return;
      }

      if (/^---+$/.test(line)) {
        closeList();
        html.push('<hr>');
        return;
      }

      const listMatch = line.match(/^[-*]\s+(.+)$/);
      const orderedMatch = line.match(/^\d+[.)、]\s+(.+)$/);
      if (listMatch || orderedMatch) {
        openList(orderedMatch ? 'ol' : 'ul');
        const content = (listMatch || orderedMatch)[1].trim();
        const field = splitField(content);
        if (field) {
          html.push(
            '<li class="summary-list-field">',
            `<strong class="summary-field-label">${renderInline(field.label)}：</strong>`,
            `<span>${renderInline(field.content)}</span>`,
            '</li>',
          );
        } else {
          html.push(`<li>${renderInline(content)}</li>`);
        }
        return;
      }

      closeList();
      const field = splitField(line, sectionKind === 'metadata');
      if (field) {
        html.push(
          '<div class="summary-field">',
          `<strong class="summary-field-label">${renderInline(field.label)}</strong>`,
          `<div class="summary-field-value">${renderInline(field.content)}</div>`,
          '</div>',
        );
        return;
      }

      html.push(`<p>${renderInline(line)}</p>`);
    });

    closeSection();
    closeList();
    html.push('</div>');
    return html.join('\n');
  }

  global.AutoPaperSummary = { render };
}(window));
