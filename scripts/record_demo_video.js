// Agent Guard - 自动化录屏脚本 (Playwright + Edge + FFmpeg)
// 将真实系统操作录制为 1080P 高清 MP4 演示视频

const path = require('path');
const fs = require('fs');
const { execSync } = require('child_process');

const PLAYWRIGHT_PATH = 'C:/Users/冯先生/.gemini/antigravity/scratch/SyncVeroHot-Promo/node_modules/playwright';
const FFMPEG_PATH = 'C:/Users/冯先生/AppData/Local/ms-playwright/ffmpeg-1013/ffmpeg-win64.exe';
const ROOT_DIR = path.resolve(__dirname, '..');
const TEMP_VIDEO_DIR = path.join(ROOT_DIR, 'docs', 'video_temp');
const FINAL_MP4_PATH = path.join(ROOT_DIR, 'docs', 'Agent_Guard_Demo_1080p.mp4');

const { chromium } = require(PLAYWRIGHT_PATH);

async function record() {
  console.log('===================================================');
  console.log('   Agent Guard V2 - 自动化录制 1080P 演示视频');
  console.log('===================================================');

  if (!fs.existsSync(TEMP_VIDEO_DIR)) {
    fs.mkdirSync(TEMP_VIDEO_DIR, { recursive: true });
  }

  // 清理临时目录下的老视频文件
  for (const f of fs.readdirSync(TEMP_VIDEO_DIR)) {
    if (f.endsWith('.webm') || f.endsWith('.mp4')) {
      fs.unlinkSync(path.join(TEMP_VIDEO_DIR, f));
    }
  }

  console.log('[--] 启动 Edge 浏览器并开启 1080P (1920x1080) 录屏...');
  const browser = await chromium.launch({
    channel: 'msedge',
    headless: true, // 自动化无头录制，确保画面平稳、无抖动、严格 1080P
  });

  const context = await browser.newContext({
    recordVideo: {
      dir: TEMP_VIDEO_DIR,
      size: { width: 1920, height: 1080 },
    },
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 1,
  });

  const page = await context.newPage();

  // 自动确认所有系统弹窗（一键重置、急停解除确认等）
  page.on('dialog', async (dialog) => {
    console.log(`[--] 自动确认系统弹窗: "${dialog.message().substring(0, 30)}..."`);
    await dialog.accept();
  });

  console.log('[--] 访问控制台首页 (http://localhost:5173) ...');
  await page.goto('http://localhost:5173', { waitUntil: 'networkidle' });
  await page.waitForTimeout(2000);

  // ----------------------------------------------------
  // 前置准备：一键重置演示数据，保证环境纯净
  // ----------------------------------------------------
  console.log('[--] 初始化重置演示环境...');
  await page.getByRole('button', { name: '演示', exact: true }).click();
  await page.waitForTimeout(1000);
  const resetBtn = page.getByRole('button', { name: '一键重置演示数据' });
  if (await resetBtn.isVisible()) {
    await resetBtn.click();
    await page.waitForTimeout(2000);
  }

  // ----------------------------------------------------
  // Act 1: 总览与仪表盘展示 (0s ~ 10s)
  // ----------------------------------------------------
  console.log('[Act 1] 展示总览仪表盘与系统监控...');
  await page.getByRole('button', { name: '总览', exact: true }).click();
  await page.waitForTimeout(5000);

  // ----------------------------------------------------
  // Act 2: 场景 B - Prompt Injection 攻击与硬阻断 (10s ~ 42s)
  // ----------------------------------------------------
  console.log('[Act 2] 切换至「实时运行」，展示攻击防御...');
  await page.getByRole('button', { name: '实时运行', exact: true }).click();
  await page.waitForTimeout(3000);

  console.log('[Act 2] 点击「演示攻击拦截（越权）」...');
  const attackBtn = page.getByRole('button', { name: '演示攻击拦截（越权）' });
  await attackBtn.hover();
  await page.waitForTimeout(1000);
  await attackBtn.click();

  // 等待 Agent 读取客户 6 备注并诱导请求 crm.export_all
  console.log('[Act 2] 观察网关识别越权请求并硬拦截 (denied)...');
  await page.waitForTimeout(5000);

  // 滚动展示拦截卡片与右侧审计流
  await page.mouse.wheel(0, 250);
  await page.waitForTimeout(6000);
  await page.mouse.wheel(0, -250);
  await page.waitForTimeout(2000);

  // ----------------------------------------------------
  // Act 3: 场景 A - 人机协同写操作审批与 scope 绑定 (42s ~ 78s)
  // ----------------------------------------------------
  console.log('[Act 3] 点击「演示 Agent 运行（跟进）」...');
  const followBtn = page.getByRole('button', { name: '演示 Agent 运行（跟进）' });
  await followBtn.hover();
  await page.waitForTimeout(1000);
  await followBtn.click();

  // 观察只读放行与敏感写操作挂起
  console.log('[Act 3] 观察 crm.read 自动放行与 mail.send 触发人工审批...');
  await page.waitForTimeout(5000);

  // 寻找待审批卡片上的「批准执行」按钮
  const approveBtn = page.getByRole('button', { name: '批准执行' }).first();
  if (await approveBtn.isVisible()) {
    console.log('[Act 3] 发现待审批卡片，高亮展示参数与 scope_hash 绑定...');
    await approveBtn.hover();
    await page.waitForTimeout(3000);

    console.log('[Act 3] 点击「批准执行」...');
    await approveBtn.click();
    await page.waitForTimeout(4000);

    // 继续推进后续步骤
    const continueBtn = page.getByRole('button', { name: '继续推进' });
    if (await continueBtn.isVisible()) {
      await continueBtn.click();
      await page.waitForTimeout(4000);
    }
  }

  // ----------------------------------------------------
  // Act 4: 场景 C - 全局人工急停制动 (Kill Switch) (78s ~ 102s)
  // ----------------------------------------------------
  console.log('[Act 4] 测试全局紧急停止制动...');
  const stopBtn = page.getByRole('button', { name: '紧急停止' });
  if (await stopBtn.isVisible()) {
    await stopBtn.hover();
    await page.waitForTimeout(1000);

    console.log('[Act 4] 触发「紧急停止」...');
    await stopBtn.click();
    await page.waitForTimeout(6000);

    // 观察急停生效状态后，点击「解除急停」恢复
    const resumeBtn = page.getByRole('button', { name: '解除急停' });
    if (await resumeBtn.isVisible()) {
      console.log('[Act 4] 解除急停恢复正常状态...');
      await resumeBtn.hover();
      await page.waitForTimeout(1000);
      await resumeBtn.click();
      await page.waitForTimeout(4000);
    }
  }

  // ----------------------------------------------------
  // Act 5: 审计哈希链展示 (102s ~ 122s)
  // ----------------------------------------------------
  console.log('[Act 5] 切换至「审计日志」Tab 展示密码学哈希链...');
  await page.getByRole('button', { name: '审计日志', exact: true }).click();
  await page.waitForTimeout(3000);

  // 缓慢向下滚动展示哈希链与全链路存证
  await page.mouse.wheel(0, 350);
  await page.waitForTimeout(3000);
  await page.mouse.wheel(0, 350);
  await page.waitForTimeout(4000);
  await page.mouse.wheel(0, -700);
  await page.waitForTimeout(2000);

  // ----------------------------------------------------
  // Act 6: 数据管理与发件箱展示 (122s ~ 135s)
  // ----------------------------------------------------
  console.log('[Act 6] 切换至「数据管理」展示客户与真实发件箱落库...');
  await page.getByRole('button', { name: '数据管理', exact: true }).click();
  await page.waitForTimeout(4000);

  console.log('[Act 6] 返回「总览」仪表盘完成收官定格...');
  await page.getByRole('button', { name: '总览', exact: true }).click();
  await page.waitForTimeout(4000);

  console.log('[--] 录制流程完成，正在关闭浏览器保存视频流...');
  await page.close();
  await context.close();
  await browser.close();

  // 查找生成的 webm 文件
  const webmFiles = fs.readdirSync(TEMP_VIDEO_DIR).filter((f) => f.endsWith('.webm'));
  if (webmFiles.length === 0) {
    throw new Error('未找到录制的 webm 视频文件');
  }

  const inputWebm = path.join(TEMP_VIDEO_DIR, webmFiles[0]);
  console.log(`[--] 捕获到原始视频录像: ${inputWebm}`);
  console.log(`[--] 正在使用 FFmpeg 转码为标准 1080P MP4: ${FINAL_MP4_PATH} ...`);

  const ffmpegCmd = `"${FFMPEG_PATH}" -y -i "${inputWebm}" -c:v libx264 -pix_fmt yuv420p -r 30 "${FINAL_MP4_PATH}"`;
  execSync(ffmpegCmd, { stdio: 'inherit' });

  if (fs.existsSync(FINAL_MP4_PATH)) {
    const stats = fs.statSync(FINAL_MP4_PATH);
    const sizeMb = (stats.size / (1024 * 1024)).toFixed(2);
    console.log('===================================================');
    console.log(`[OK] 成功录制并导出 1080P 演示视频: ${FINAL_MP4_PATH}`);
    console.log(`     文件大小: ${sizeMb} MB`);
    console.log('===================================================');
  }
}

record().catch((err) => {
  console.error('[错误] 录屏执行失败:', err);
  process.exit(1);
});
