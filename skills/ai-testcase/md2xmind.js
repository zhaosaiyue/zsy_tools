#!/usr/bin/env node
/**
 * 将 ai-testcase 生成的 Markdown 转换为 .xmind 文件
 *
 *
 * 用法：node tools/md2xmind.js <input.md> [output.xmind]
 *       output 省略时在同目录生成同名 .xmind 文件
 */

'use strict';

const fs = require('fs');
const path = require('path');
const JSZip = require('jszip');
const crypto = require('crypto');

// ─── 工具函数 ────────────────────────────────────────────────────────────────

function uuid() {
  return crypto.randomUUID();
}

/** 构造一个 topic 节点，children 为数组（可空） */
function makeTopic(title, children = [], notes = null) {
  const topic = { id: uuid(), class: 'topic', title, titleUnedited: false };
  if (notes) {
    topic.notes = { plain: { content: notes }, realHTML: { content: notes } };
    topic.notesDisplay = 'block';
  }
  if (children.length > 0) {
    topic.children = { attached: children };
  }
  return topic;
}

// ─── Markdown 解析 ───────────────────────────────────────────────────────────

/**
 * 把 MD 行解析成带层级的 token 列表
 * 层级规则：
 *   # → level 1  (根标题，取作 rootTopic title)
 *   ## → level 2
 *   ### → level 3
 *   #### → level 4
 *   - / * (indent 0) → level 5
 *   (indent 2) → level 6
 *   (indent 4) → level 7
 *   ...以此类推，每多 2 格 indent +1
 *
 * blockquote (> ...) 归入前一个 # 节点的 notes
 */
function parseMarkdown(text) {
  const lines = text.split('\n');
  const tokens = [];
  let pendingNotes = [];

  for (let raw of lines) {
    const line = raw;

    // 空行
    if (line.trim() === '') continue;

    // blockquote → notes（附加到上一个 level1 token）
    if (/^>\s?/.test(line)) {
      pendingNotes.push(line.replace(/^>\s?/, ''));
      continue;
    }

    // 标题
    const hMatch = line.match(/^(#{1,6})\s+(.*)/);
    if (hMatch) {
      const level = hMatch[1].length;
      const title = hMatch[2].trim();
      // 如果有待归入的 notes，合并到上一个同级 token
      if (pendingNotes.length > 0 && tokens.length > 0) {
        tokens[tokens.length - 1].notes = pendingNotes.join('\n');
        pendingNotes = [];
      }
      tokens.push({ level, title, notes: null });
      continue;
    }

    // 列表项（支持 - 和 *）
    const listMatch = line.match(/^(\s*)[-*]\s+(.*)/);
    if (listMatch) {
      const indent = listMatch[1].length;
      // indent 0 → level 5，每 2 格 +1
      const level = 5 + Math.floor(indent / 2);
      const title = listMatch[2].trim();
      if (pendingNotes.length > 0 && tokens.length > 0) {
        tokens[tokens.length - 1].notes = pendingNotes.join('\n');
        pendingNotes = [];
      }
      tokens.push({ level, title, notes: null });
      continue;
    }

    // 其他普通行（如表格行、分割线等）忽略
  }

  // 末尾残余 notes
  if (pendingNotes.length > 0 && tokens.length > 0) {
    tokens[tokens.length - 1].notes = pendingNotes.join('\n');
  }

  return tokens;
}

/**
 * 将 token 列表构建成 XMind topic 树
 * 返回 { rootTitle, rootNotes, children }
 */
function buildTree(tokens) {
  if (tokens.length === 0) return { rootTitle: '测试用例', rootNotes: null, children: [] };

  // 第一个 level=1 的 token 作为根
  let rootTitle = '测试用例';
  let rootNotes = null;
  let startIdx = 0;

  if (tokens[0].level === 1) {
    rootTitle = tokens[0].title;
    rootNotes = tokens[0].notes;
    startIdx = 1;
  }

  // 用栈构建树，stack[i] = { level, children[] }
  // stack 顶部始终是"当前父节点的 children 数组"
  const root = { level: 1, topic: null, children: [] };
  const stack = [root]; // stack 中存 { level, children }

  for (let i = startIdx; i < tokens.length; i++) {
    const tok = tokens[i];
    const topic = makeTopic(tok.title, [], tok.notes);

    // 弹栈直到找到 level 小于当前 token 的节点
    while (stack.length > 1 && stack[stack.length - 1].level >= tok.level) {
      stack.pop();
    }

    // 当前父节点的 children 数组
    const parentChildren = stack[stack.length - 1].children;
    parentChildren.push(topic);

    // 把当前 topic 入栈（作为后续更深节点的父）
    stack.push({ level: tok.level, children: topic.children ? topic.children.attached : (() => {
      topic.children = { attached: [] };
      return topic.children.attached;
    })() });
  }

  return { rootTitle, rootNotes, children: root.children };
}

// ─── XMind 画布主题（从真实文件提取，保持原始样式）────────────────────────────

const XMIND_THEME = {
  map: {
    id: uuid(),
    properties: {
      "svg:fill": "#ffffff",
      "multi-line-colors": "#FF6B6B #FF9F69 #97D3B6 #88E2D7 #6FD0F9 #E18BEE",
      "color-list": "#FF6B6B #FF9F69 #97D3B6 #88E2D7 #6FD0F9 #E18BEE",
      "line-tapered": "none"
    }
  },
  centralTopic: {
    id: uuid(),
    properties: {
      "fo:font-family": "Droid Serif",
      "fo:font-size": "30pt",
      "fo:font-weight": "400",
      "fo:font-style": "normal",
      "fo:color": "inherited",
      "fo:text-transform": "manual",
      "fo:text-decoration": "none",
      "fo:text-align": "center",
      "svg:fill": "#000000",
      "fill-pattern": "solid",
      "line-width": "3pt",
      "line-color": "#ADADAD",
      "line-pattern": "solid",
      "border-line-color": "#000000",
      "border-line-width": "inherited",
      "border-line-pattern": "inherited",
      "shape-class": "org.xmind.topicShape.roundedRect",
      "line-class": "org.xmind.branchConnection.roundedElbow",
      "arrow-end-class": "org.xmind.arrowShape.none",
      "alignment-by-level": "inactived"
    }
  },
  mainTopic: {
    id: uuid(),
    properties: {
      "fo:font-family": "Droid Serif",
      "fo:font-size": "18pt",
      "fo:font-weight": "400",
      "fo:font-style": "normal",
      "fo:color": "inherited",
      "fo:text-transform": "manual",
      "fo:text-decoration": "none",
      "fo:text-align": "left",
      "svg:fill": "inherited",
      "fill-pattern": "none",
      "line-width": "inherited",
      "line-color": "inherited",
      "line-pattern": "inherited",
      "border-line-color": "inherited",
      "border-line-width": "0pt",
      "border-line-pattern": "inherited",
      "shape-class": "org.xmind.topicShape.roundedRect",
      "line-class": "org.xmind.branchConnection.roundedElbow",
      "arrow-end-class": "inherited",
      "alignment-by-level": "inherited"
    }
  },
  subTopic: {
    id: uuid(),
    properties: {
      "fo:font-family": "Droid Serif",
      "fo:font-size": "14pt",
      "fo:font-weight": "400",
      "fo:font-style": "normal",
      "fo:color": "inherited",
      "fo:text-transform": "manual",
      "fo:text-decoration": "none",
      "fo:text-align": "left",
      "svg:fill": "inherited",
      "fill-pattern": "none",
      "line-width": "2pt",
      "line-color": "inherited",
      "line-pattern": "inherited",
      "border-line-color": "inherited",
      "border-line-width": "0pt",
      "border-line-pattern": "inherited",
      "shape-class": "org.xmind.topicShape.roundedRect",
      "line-class": "org.xmind.branchConnection.roundedElbow",
      "arrow-end-class": "inherited",
      "alignment-by-level": "inherited"
    }
  },
  floatingTopic: {
    id: uuid(),
    properties: {
      "fo:font-family": "Droid Serif",
      "fo:font-size": "14pt",
      "fo:font-weight": "400",
      "fo:font-style": "normal",
      "fo:color": "inherited",
      "fo:text-transform": "manual",
      "fo:text-decoration": "none",
      "fo:text-align": "center",
      "svg:fill": "#EEEBEE",
      "fill-pattern": "solid",
      "line-width": "inherited",
      "line-color": "inherited",
      "line-pattern": "solid",
      "border-line-color": "#EEEBEE",
      "border-line-width": "0pt",
      "border-line-pattern": "inherited",
      "shape-class": "org.xmind.topicShape.roundedRect",
      "line-class": "org.xmind.branchConnection.roundedElbow",
      "arrow-end-class": "org.xmind.arrowShape.none",
      "alignment-by-level": "inherited"
    }
  },
  summaryTopic: {
    id: uuid(),
    properties: {
      "fo:font-family": "Droid Serif",
      "fo:font-size": "14pt",
      "fo:font-weight": "400",
      "fo:font-style": "normal",
      "fo:color": "inherited",
      "fo:text-transform": "manual",
      "fo:text-decoration": "none",
      "fo:text-align": "center",
      "svg:fill": "#000000",
      "fill-pattern": "solid",
      "line-width": "inherited",
      "line-color": "inherited",
      "line-pattern": "inherited",
      "border-line-color": "#000000",
      "border-line-width": "0pt",
      "border-line-pattern": "inherited",
      "shape-class": "org.xmind.topicShape.roundedRect",
      "line-class": "org.xmind.branchConnection.roundedElbow",
      "arrow-end-class": "inherited",
      "alignment-by-level": "inherited"
    }
  },
  calloutTopic: {
    id: uuid(),
    properties: {
      "fo:font-family": "Droid Serif",
      "fo:font-size": "14pt",
      "fo:font-weight": "400",
      "fo:font-style": "normal",
      "fo:color": "inherited",
      "fo:text-transform": "manual",
      "fo:text-decoration": "none",
      "fo:text-align": "left",
      "svg:fill": "#000000",
      "fill-pattern": "solid",
      "line-width": "inherited",
      "line-color": "inherited",
      "line-pattern": "inherited",
      "border-line-color": "#000000",
      "border-line-width": "inherited",
      "border-line-pattern": "inherited",
      "shape-class": "org.xmind.topicShape.roundedRect",
      "line-class": "org.xmind.branchConnection.roundedElbow",
      "arrow-end-class": "inherited",
      "alignment-by-level": "inherited"
    }
  },
  importantTopic: {
    id: uuid(),
    properties: {
      "fo:font-weight": "bold",
      "svg:fill": "#7F00AC",
      "fill-pattern": "solid",
      "border-line-color": "#7F00AC",
      "border-line-width": "0"
    }
  },
  minorTopic: {
    id: uuid(),
    properties: {
      "fo:font-weight": "bold",
      "svg:fill": "#82004A",
      "fill-pattern": "solid",
      "border-line-color": "#82004A",
      "border-line-width": "0"
    }
  },
  expiredTopic: {
    id: uuid(),
    properties: {
      "fo:text-decoration": "line-through",
      "fill-pattern": "none"
    }
  },
  boundary: {
    id: uuid(),
    properties: {
      "fo:font-family": "Droid Serif",
      "fo:font-size": "14pt",
      "fo:font-weight": "400",
      "fo:font-style": "normal",
      "fo:color": "inherited",
      "fo:text-transform": "manual",
      "fo:text-decoration": "none",
      "fo:text-align": "center",
      "svg:fill": "#9B9B9B",
      "fill-pattern": "solid",
      "line-width": "2",
      "line-color": "#00000066",
      "line-pattern": "dash",
      "shape-class": "org.xmind.boundaryShape.roundedRect"
    }
  },
  relationship: {
    id: uuid(),
    properties: {
      "fo:font-family": "Droid Serif",
      "fo:font-size": "13pt",
      "fo:font-weight": "400",
      "fo:font-style": "normal",
      "fo:color": "inherited",
      "fo:text-transform": "manual",
      "fo:text-decoration": "none",
      "fo:text-align": "center",
      "line-width": "2",
      "line-color": "#00000066",
      "line-pattern": "dash",
      "shape-class": "org.xmind.relationshipShape.curved",
      "arrow-begin-class": "org.xmind.arrowShape.none",
      "arrow-end-class": "org.xmind.arrowShape.triangle"
    }
  },
  skeletonThemeId: "c1fbada1b45ba2e3bfc3b8b57b",
  colorThemeId: "Dawn-#ffffff-MULTI_LINE_COLORS"
};

// ─── 生成 XMind 文件 ─────────────────────────────────────────────────────────

async function generateXmind(mdPath, outPath) {
  const mdText = fs.readFileSync(mdPath, 'utf8');
  const tokens = parseMarkdown(mdText);
  const { rootTitle, rootNotes, children } = buildTree(tokens);

  const sheetId = uuid();
  const rootTopicId = uuid();
  const rootTopic = makeTopic(rootTitle, children, rootNotes);
  rootTopic.id = rootTopicId;
  rootTopic.structureClass = 'org.xmind.ui.logic.right';

  const contentJson = [
    {
      id: sheetId,
      revisionId: uuid(),
      class: 'sheet',
      title: 'Map',
      arrangeableLayerOrder: [rootTopicId],
      zones: [],
      extensions: [
        {
          provider: 'org.xmind.ui.skeleton.structure.style',
          content: { centralTopic: 'org.xmind.ui.logic.right' }
        }
      ],
      theme: XMIND_THEME,
      rootTopic,
    }
  ];

  const metadataJson = {
    dataStructureVersion: '3',
    creator: { name: 'md2xmind', version: '1.0.0' },
    activeSheetId: sheetId,
    layoutEngineVersion: '5'
  };

  const manifestJson = {
    'file-entries': {
      'content.json': {},
      'metadata.json': {}
    }
  };

  const zip = new JSZip();
  zip.file('content.json', JSON.stringify(contentJson, null, 2));
  zip.file('metadata.json', JSON.stringify(metadataJson));
  zip.file('manifest.json', JSON.stringify(manifestJson));

  const buffer = await zip.generateAsync({ type: 'nodebuffer', compression: 'DEFLATE' });
  fs.writeFileSync(outPath, buffer);

  return { rootTitle, topicCount: tokens.length };
}

// ─── 入口 ────────────────────────────────────────────────────────────────────

async function main() {
  const args = process.argv.slice(2);
  if (args.length === 0) {
    console.error('用法：node tools/md2xmind.js <input.md> [output.xmind]');
    process.exit(1);
  }

  const mdPath = path.resolve(args[0]);
  if (!fs.existsSync(mdPath)) {
    console.error(`文件不存在：${mdPath}`);
    process.exit(1);
  }

  const outPath = args[1]
    ? path.resolve(args[1])
    : mdPath.replace(/\.md$/, '.xmind');

  try {
    const { rootTitle, topicCount } = await generateXmind(mdPath, outPath);
    console.log(`✅ 转换完成`);
    console.log(`   标题：${rootTitle}`);
    console.log(`   节点数：${topicCount}`);
    console.log(`   输出：${outPath}`);
  } catch (err) {
    console.error('转换失败：', err.message);
    process.exit(1);
  }
}

main();