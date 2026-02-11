/**
 * CPA-XX i18n Layer - English & Vietnamese support
 * Zero changes to app.py, single <script> tag in index.html
 *
 * Usage: Add <script src="i18n.js"></script> before </body> in index.html
 * Language is stored in localStorage('lang'), defaults to 'zh'
 */
(function () {
    'use strict';

    // ==================== Translation Dictionaries ====================
    const T = {
        // ---- Page / Header ----
        'CPA-XX 管理面板': { en: 'CPA-XX Dashboard', vi: 'CPA-XX Bảng điều khiển' },
        '服务': { en: 'Service', vi: 'Dịch vụ' },
        '版本': { en: 'Version', vi: 'Phiên bản' },
        '请求': { en: 'Requests', vi: 'Yêu cầu' },
        '模型': { en: 'Models', vi: 'Mô hình' },
        '健康': { en: 'Health', vi: 'Sức khỏe' },
        '刷新': { en: 'Refresh', vi: 'Làm mới' },
        '切换主题': { en: 'Toggle theme', vi: 'Chuyển chủ đề' },

        // ---- Update Banner ----
        '发现新版本可用！当前:': { en: 'New version available! Current:', vi: 'Có phiên bản mới! Hiện tại:' },
        '→ 最新:': { en: '\u2192 Latest:', vi: '\u2192 Mới nhất:' },
        '立即更新': { en: 'Update Now', vi: 'Cập nhật ngay' },

        // ---- Quote Card ----
        '名人语录': { en: 'Famous Quotes', vi: 'Danh ngôn' },
        '随机语录': { en: 'Random Quotes', vi: 'Ngẫu nhiên' },
        '刷新间隔': { en: 'Interval', vi: 'Chu kỳ' },
        '分钟': { en: 'min', vi: 'phút' },
        '换一条': { en: 'Next', vi: 'Tiếp' },
        '添加': { en: 'Add', vi: 'Thêm' },

        // ---- Request Stats Card ----
        '请求统计': { en: 'Request Stats', vi: 'Thống kê yêu cầu' },
        'API 使用监控': { en: 'API Usage Monitor', vi: 'Giám sát sử dụng API' },
        '清空': { en: 'Clear', vi: 'Xóa' },
        '总请求数': { en: 'Total Requests', vi: 'Tổng yêu cầu' },
        '百万Tokens': { en: 'M Tokens', vi: 'Triệu Tokens' },
        '美元': { en: 'USD', vi: 'USD' },
        '成功': { en: 'Success', vi: 'Thành công' },
        '失败': { en: 'Failed', vi: 'Thất bại' },
        'Token 价格设置（输入/输出/缓存）': { en: 'Token Pricing (Input/Output/Cache)', vi: 'Giá Token (Nhập/Xuất/Bộ nhớ)' },
        '输入': { en: 'Input', vi: 'Nhập' },
        '输出': { en: 'Output', vi: 'Xuất' },
        '缓存': { en: 'Cache', vi: 'Bộ nhớ đệm' },
        '保存价格': { en: 'Save Pricing', vi: 'Lưu giá' },

        // ---- Models Card ----
        '可用模型': { en: 'Available Models', vi: 'Mô hình khả dụng' },
        '加载中...': { en: 'Loading...', vi: 'Đang tải...' },
        '未找到模型': { en: 'No models found', vi: 'Không tìm thấy mô hình' },
        '获取模型失败': { en: 'Failed to load models', vi: 'Tải mô hình thất bại' },
        '其他': { en: 'Other', vi: 'Khác' },

        // ---- Health Card ----
        '健康状态': { en: 'Health Status', vi: 'Trạng thái hệ thống' },
        '系统健康检查': { en: 'System Health Check', vi: 'Kiểm tra sức khỏe hệ thống' },
        '状态': { en: 'Status', vi: 'Trạng thái' },
        '运行时间': { en: 'Uptime', vi: 'Thời gian hoạt động' },
        '整体状态': { en: 'Overall', vi: 'Tổng thể' },
        '服务进程': { en: 'Service Process', vi: 'Tiến trình dịch vụ' },
        '服务状态': { en: 'Service Status', vi: 'Trạng thái dịch vụ' },
        '配置文件': { en: 'Config File', vi: 'Tệp cấu hình' },
        '磁盘空间': { en: 'Disk Space', vi: 'Dung lượng đĩa' },
        '内存使用': { en: 'Memory Usage', vi: 'Sử dụng bộ nhớ' },
        '认证文件': { en: 'Auth Files', vi: 'Tệp xác thực' },
        'API端口': { en: 'API Port', vi: 'Cổng API' },
        '启动': { en: 'Start', vi: 'Khởi động' },
        '停止': { en: 'Stop', vi: 'Dừng' },
        '重启': { en: 'Restart', vi: 'Khởi động lại' },
        '运行检查': { en: 'Run Check', vi: 'Kiểm tra' },
        '健康': { en: 'Healthy', vi: 'Khỏe mạnh' },
        '警告': { en: 'Warning', vi: 'Cảnh báo' },
        '异常': { en: 'Error', vi: 'Lỗi' },
        '正常': { en: 'Normal', vi: 'Bình thường' },

        // ---- Health check messages (from backend API) ----
        '服务运行中': { en: 'Service running', vi: 'Dịch vụ đang chạy' },
        '服务未运行': { en: 'Service not running', vi: 'Dịch vụ không chạy' },
        '配置文件有效': { en: 'Config file valid', vi: 'Tệp cấu hình hợp lệ' },
        '无法获取磁盘信息': { en: 'Cannot get disk info', vi: 'Không thể lấy thông tin đĩa' },
        '无法获取内存信息': { en: 'Cannot get memory info', vi: 'Không thể lấy thông tin bộ nhớ' },
        '认证目录不存在': { en: 'Auth directory not found', vi: 'Thư mục xác thực không tồn tại' },
        '无法检测端口状态': { en: 'Cannot detect port status', vi: 'Không thể kiểm tra trạng thái cổng' },
        '开放': { en: 'open', vi: 'mở' },
        '关闭': { en: 'closed', vi: 'đóng' },

        // ---- Version Update Card ----
        '版本更新': { en: 'Version Update', vi: 'Cập nhật phiên bản' },
        '自动同步 GitHub': { en: 'Auto-sync GitHub', vi: 'Tự động bộ GitHub' },
        '当前': { en: 'Current', vi: 'Hiện tại' },
        '最新': { en: 'Latest', vi: 'Mới nhất' },
        '上次更新: -': { en: 'Last update: -', vi: 'Cập nhật cuối: -' },
        '检查': { en: 'Check', vi: 'Kiểm tra' },
        '更新': { en: 'Update', vi: 'Cập nhật' },
        '强制': { en: 'Force', vi: 'Buộc' },

        // ---- Auto Update Card ----
        '自动更新': { en: 'Auto Update', vi: 'Tự động cập nhật' },
        '智能更新设置': { en: 'Smart Update Settings', vi: 'Cài đặt cập nhật thông minh' },
        '已开启': { en: 'On', vi: 'Đã bật' },
        '已关闭': { en: 'Off', vi: 'Đã tắt' },
        '检查间隔（检查更新的间隔）': { en: 'Check Interval', vi: 'Chu kỳ kiểm tra' },
        '空闲阈值（多久没有请求日志则检查更新）': { en: 'Idle Threshold (check update when no requests)', vi: 'Ngưỡng rảnh (kiểm tra khi không có yêu cầu)' },
        '保存设置': { en: 'Save Settings', vi: 'Lưu cài đặt' },

        // ---- Routing Card ----
        '路由策略': { en: 'Routing Strategy', vi: 'Chiến lược định tuyến' },
        '负载均衡模式': { en: 'Load Balancing Mode', vi: 'Chế độ cân bằng tải' },
        '当前策略': { en: 'Current Strategy', vi: 'Chiến lược hiện tại' },
        '轮询 (Round Robin)': { en: 'Round Robin', vi: 'Luân phiên (Round Robin)' },
        '填充优先 (Fill First)': { en: 'Fill First', vi: 'Ưu tiên lấp đầy (Fill First)' },
        '应用': { en: 'Apply', vi: 'Áp dụng' },

        // ---- Config Card ----
        '配置管理': { en: 'Config Management', vi: 'Quản lý cấu hình' },
        '编辑配置': { en: 'Edit Config', vi: 'Sửa cấu hình' },
        '验证配置': { en: 'Validate Config', vi: 'Kiểm tra cấu hình' },
        '重载配置': { en: 'Reload Config', vi: 'Tải lại cấu hình' },

        // ---- CPU Card ----
        'CPU 使用率': { en: 'CPU Usage', vi: 'Sử dụng CPU' },
        '1分钟': { en: '1 min', vi: '1 phút' },
        '5分钟': { en: '5 min', vi: '5 phút' },
        '15分钟': { en: '15 min', vi: '15 phút' },

        // ---- Memory Card ----
        '内存使用率': { en: 'Memory Usage', vi: 'Sử dụng bộ nhớ' },
        '可用': { en: 'Available', vi: 'Khả dụng' },
        'cliproxy 内存': { en: 'cliproxy Mem', vi: 'cliproxy RAM' },
        '未配置': { en: 'Not configured', vi: 'Chưa cấu hình' },

        // ---- Disk Card ----
        '磁盘使用率': { en: 'Disk Usage', vi: 'Sử dụng đĩa' },

        // ---- Export Card ----
        '数据导出': { en: 'Data Export', vi: 'Xuất dữ liệu' },
        '导出日志与统计': { en: 'Export Logs & Stats', vi: 'Xuất nhật ký & thống kê' },
        '导出日志': { en: 'Export Logs', vi: 'Xuất nhật ký' },
        '导出统计': { en: 'Export Stats', vi: 'Xuất thống kê' },
        '导出配置': { en: 'Export Config', vi: 'Xuất cấu hình' },

        // ---- Log Panel ----
        'CLIProxy 日志': { en: 'CLIProxy Logs', vi: 'Nhật ký CLIProxy' },
        '屏蔽本地': { en: 'Hide local', vi: 'Ẩn nội bộ' },
        '清空统计': { en: 'Clear stats', vi: 'Xóa thống kê' },
        '暂无日志': { en: 'No logs yet', vi: 'Chưa có nhật ký' },
        '暂无日志（已过滤本地请求）': { en: 'No logs (local requests filtered)', vi: 'Chưa có nhật ký (yêu cầu nội bộ đã lọc)' },
        '日志已清空': { en: 'Logs cleared', vi: 'Đã xóa nhật ký' },
        '暂无日志可清空': { en: 'No logs to clear', vi: 'Không có nhật ký để xóa' },

        // ---- Config Modal ----
        '编辑配置文件': { en: 'Edit Config File', vi: 'Sửa tệp cấu hình' },
        '验证': { en: 'Validate', vi: 'Kiểm tra' },
        '取消': { en: 'Cancel', vi: 'Hủy' },
        '保存': { en: 'Save', vi: 'Lưu' },
        '配置验证结果': { en: 'Validation Result', vi: 'Kết quả kiểm tra' },
        '确定': { en: 'OK', vi: 'Đồng ý' },

        // ---- JS Dynamic Strings (toast, confirm, etc.) ----
        '运行中': { en: 'Running', vi: 'Đang chạy' },
        '已停止': { en: 'Stopped', vi: 'Đã dừng' },
        '空闲中': { en: 'Idle', vi: 'Rảnh' },
        '处理中': { en: 'Processing', vi: 'Đang xử lý' },

        // ---- Toast messages ----
        '统计数据已清空': { en: 'Stats cleared', vi: 'Đã xóa thống kê' },
        '价格已保存': { en: 'Pricing saved', vi: 'Đã lưu giá' },
        '保存失败': { en: 'Save failed', vi: 'Lưu thất bại' },
        '语录已添加': { en: 'Quote added', vi: 'Đã thêm danh ngôn' },
        '添加失败': { en: 'Add failed', vi: 'Thêm thất bại' },
        '加载配置失败': { en: 'Failed to load config', vi: 'Tải cấu hình thất bại' },
        '配置内容为空': { en: 'Config content is empty', vi: 'Nội dung cấu hình trống' },
        '设置已保存': { en: 'Settings saved', vi: 'Đã lưu cài đặt' },
        '已是最新版本': { en: 'Already up to date', vi: 'Đã là phiên bản mới nhất' },
        '更新请求已发送': { en: 'Update request sent', vi: 'Yêu cầu cập nhật đã gửi' },
        '设置失败': { en: 'Settings failed', vi: 'Cài đặt thất bại' },
        '验证请求失败': { en: 'Validation request failed', vi: 'Yêu cầu kiểm tra thất bại' },
        '请输入有效数字': { en: 'Please enter a valid number', vi: 'Vui lòng nhập số hợp lệ' },
        '空闲阈值必须大于等于1分钟': { en: 'Idle threshold must be at least 1 minute', vi: 'Ngưỡng rảnh phải \u2265 1 phút' },
        '检查间隔必须大于等于1分钟': { en: 'Check interval must be at least 1 minute', vi: 'Chu kỳ kiểm tra phải \u2265 1 phút' },
        '清空失败': { en: 'Clear failed', vi: 'Xóa thất bại' },

        // ---- Confirm dialogs ----
        '确定要清空所有请求统计数据吗？': { en: 'Clear all request statistics?', vi: 'Xóa toàn bộ thống kê yêu cầu?' },
        '确定要清空日志文件吗？': { en: 'Clear log file?', vi: 'Xóa tệp nhật ký?' },

        // ---- Prompt dialogs ----
        '请输入语录（格式：内容 出自：作者）': { en: 'Enter quote (format: content by: author)', vi: 'Nhập danh ngôn (định dạng: nội dung từ: tác giả)' },

        // ---- Service action toasts ----
        '启动成功': { en: 'Started successfully', vi: 'Khởi động thành công' },
        '启动失败': { en: 'Start failed', vi: 'Khởi động thất bại' },
        '停止成功': { en: 'Stopped successfully', vi: 'Dừng thành công' },
        '停止失败': { en: 'Stop failed', vi: 'Dừng thất bại' },
        '重启成功': { en: 'Restarted successfully', vi: 'Khởi động lại thành công' },
        '重启失败': { en: 'Restart failed', vi: 'Khởi động lại thất bại' },

        // ---- Validation results ----
        '✓ 配置格式有效': { en: '\u2713 Config format is valid', vi: '\u2713 Định dạng cấu hình hợp lệ' },
        '✗ 配置格式无效': { en: '\u2717 Config format is invalid', vi: '\u2717 Định dạng cấu hình không hợp lệ' },
        '警告:': { en: 'Warnings:', vi: 'Cảnh báo:' },
        '错误:': { en: 'Errors:', vi: 'Lỗi:' },

        // ---- Update history ----
        '暂无记录': { en: 'No record', vi: 'Chưa có' },
        '历史:': { en: 'History:', vi: 'Lịch sử:' },

        // ---- System info labels ----
        '核心': { en: 'cores', vi: 'lõi' },

        // ---- Misc toast/status ----
        '保存成功，请重载配置': { en: 'Saved. Please reload config.', vi: 'Đã lưu. Vui lòng tải lại cấu hình.' },
        '未知错误': { en: 'Unknown error', vi: 'Lỗi không xác định' },
        '空闲阈值保存失败': { en: 'Idle threshold save failed', vi: 'Lưu ngưỡng rảnh thất bại' },
        '检查间隔保存失败': { en: 'Interval save failed', vi: 'Lưu chu kỳ thất bại' },

        // ---- Backend API response messages ----
        '欢迎回来，祝你今天高效完成任务。': { en: 'Welcome back. Have a productive day!', vi: 'Chào mừng trở lại. Chúc một ngày làm việc hiệu quả!' },
        '系统': { en: 'System', vi: 'Hệ thống' },
        '配置重载信号已发送': { en: 'Config reload signal sent', vi: 'Đã gửi tín hiệu tải lại cấu hình' },
        '已重启服务以应用配置': { en: 'Service restarted to apply config', vi: 'Đã khởi động lại dịch vụ để áp dụng cấu hình' },
        'pyyaml未安装，无法解析配置': { en: 'pyyaml not installed, cannot parse config', vi: 'Chưa cài pyyaml, không thể phân tích cấu hình' },
        'pyyaml未安装,无法解析配置': { en: 'pyyaml not installed, cannot parse config', vi: 'Chưa cài pyyaml, không thể phân tích cấu hình' },
        'pyyaml未安装，无法修改配置': { en: 'pyyaml not installed, cannot modify config', vi: 'Chưa cài pyyaml, không thể sửa cấu hình' },
        'pyyaml未安装,无法修改配置': { en: 'pyyaml not installed, cannot modify config', vi: 'Chưa cài pyyaml, không thể sửa cấu hình' },
        'pyyaml未安装，无法进行深度验证': { en: 'pyyaml not installed, deep validation unavailable', vi: 'Chưa cài pyyaml, không thể kiểm tra sâu' },
        'pyyaml未安装,无法进行深度验证': { en: 'pyyaml not installed, deep validation unavailable', vi: 'Chưa cài pyyaml, không thể kiểm tra sâu' },
        'pyyaml未安装，无法解析模型列表': { en: 'pyyaml not installed, cannot parse model list', vi: 'Chưa cài pyyaml, không thể phân tích danh sách mô hình' },

        // ---- Config validation errors (from backend) ----
        '配置必须是一个字典/对象': { en: 'Config must be a dict/object', vi: 'Cấu hình phải là dict/object' },
        '端口必须是1-65535之间的整数': { en: 'Port must be integer between 1-65535', vi: 'Cổng phải là số nguyên từ 1-65535' },
        'providers必须是一个数组': { en: 'providers must be an array', vi: 'providers phải là mảng' },

        // ---- Quote format error ----
        '格式错误，请使用"内容 出自：作者"': { en: 'Invalid format. Use "content by: author"', vi: 'Sai định dạng. Dùng "nội dung từ: tác giả"' },

        // ---- Connection test ----
        '外网连接': { en: 'Internet', vi: 'Kết nối mạng' },
        '网络正常': { en: 'Network OK', vi: 'Mạng bình thường' },
        '无法连接外网': { en: 'Cannot connect to internet', vi: 'Không thể kết nối internet' },
        '连接失败': { en: 'Connection failed', vi: 'Kết nối thất bại' },

        // ---- Log filter tooltip ----
        '隐藏来自 127.0.0.1 的请求日志': { en: 'Hide logs from 127.0.0.1', vi: 'Ẩn nhật ký từ 127.0.0.1' },
        '清空显示': { en: 'Clear display', vi: 'Xóa hiển thị' },

        // ---- Uptime units (from backend format_uptime) ----
        '秒': { en: 's', vi: 'giây' },
        '小时': { en: 'h', vi: 'giờ' },
        '天': { en: 'd', vi: 'ngày' },
        '分': { en: 'm', vi: 'phút' },
    };

    // ==================== Regex-based patterns for dynamic strings ====================
    const PATTERNS = {
        en: [
            // Model count
            [/^共 (\d+) 个模型$/, (m) => `${m[1]} models`],
            // Model group with count: 其他（3）
            [/^其他（(\d+)）$/, (m) => `Other (${m[1]})`],
            // Quote font size buttons
            [/^语录[：:](\d+) px$/, (m) => `Quote: ${m[1]} px`],
            [/^作者[：:](\d+) px$/, (m) => `Author: ${m[1]} px`],
            // Font size prompt
            [/^请输入(语录|作者)字号\(px\)$/, (m) => `Enter ${m[1] === '语录' ? 'quote' : 'author'} font size (px)`],
            // Token labels in stats
            [/^输入[：:]/, () => 'Input: '],
            [/^输出[：:]/, () => 'Output: '],
            [/^缓存[：:]/, () => 'Cache: '],
            // System info
            [/^CPU 型号[：:](.*)$/, (m) => `CPU Model: ${m[1]}`],
            [/^云厂商[：:](.*)$/, (m) => `Cloud: ${m[1]}`],
            [/^系统版本[：:](.*)$/, (m) => `OS: ${m[1]}`],
            [/^(\d+) 核心 \| (.+)$/, (m) => `${m[1]} cores | ${m[2]}`],
            // Uptime: X秒, X分钟, X小时Y分, X天Y小时
            [/^(\d+)秒$/, (m) => `${m[1]}s`],
            [/^(\d+)分钟$/, (m) => `${m[1]}min`],
            [/^(\d+)小时(\d+)分$/, (m) => `${m[1]}h${m[2]}m`],
            [/^(\d+)天(\d+)小时$/, (m) => `${m[1]}d${m[2]}h`],
            // Update history
            [/^上次更新: (.+)$/, (m) => {
                let t = m[1];
                t = t.replace('暂无记录', 'No record');
                t = t.replace(/ 分钟前/, ' min ago');
                t = t.replace(/ 小时前/, ' hours ago');
                t = t.replace(/ 天前/, ' days ago');
                return `Last update: ${t}`;
            }],
            [/(\d+(?:\.\d+)?)\s*分钟前/, (m) => `${m[1]} min ago`],
            [/(\d+(?:\.\d+)?)\s*小时前/, (m) => `${m[1]} hours ago`],
            [/(\d+(?:\.\d+)?)\s*天前/, (m) => `${m[1]} days ago`],
            [/^历史: /, () => 'History: '],
            // Update check
            [/^发现新版本: (.+)$/, (m) => `New version: ${m[1]}`],
            // Service actions: X成功/X失败
            [/^(启动|停止|重启)(成功|失败)$/, (m) => {
                const a = { '启动': 'Start', '停止': 'Stop', '重启': 'Restart' };
                const r = m[2] === '成功' ? 'succeeded' : 'failed';
                return `${a[m[1]] || m[1]} ${r}`;
            }],
            // Error message prefixes
            [/^清空失败: (.+)$/, (m) => `Clear failed: ${m[1]}`],
            [/^保存失败: (.+)$/, (m) => `Save failed: ${m[1]}`],
            [/^部分设置已保存: (.+)$/, (m) => `Partial settings saved: ${m[1]}`],
            [/^重载失败: (.+)$/, (m) => `Reload failed: ${m[1]}`],
            // Routing
            [/^路由策略已设置为 (.+)$/, (m) => `Routing set to ${m[1]}`],
            [/^无效的策略[，,]可选: (.+)$/, (m) => `Invalid strategy. Options: ${m[1]}`],
            // Health check messages from backend
            [/^配置错误: (.+)$/, (m) => `Config error: ${m[1]}`],
            [/^已使用 ([\d.]+)%$/, (m) => `${m[1]}% used`],
            [/^找到 (\d+) 个凭证文件$/, (m) => `Found ${m[1]} credential files`],
            [/^端口 (\d+) (开放|关闭)$/, (m) => `Port ${m[1]} ${m[2] === '开放' ? 'open' : 'closed'}`],
            [/^端口 (\d+) 正常$/, (m) => `Port ${m[1]} OK`],
            // Config validation errors from backend
            [/^缺少必需字段: (.+)$/, (m) => `Missing required field: ${m[1]}`],
            [/^provider\[(\d+)\] 必须是一个对象$/, (m) => `provider[${m[1]}] must be an object`],
            [/^provider\[(\d+)\] 缺少(\w+)字段$/, (m) => `provider[${m[1]}] missing ${m[2]} field`],
            [/^未知的路由策略: (.+)[，,]有效值: (.+)$/, (m) => `Unknown routing strategy: ${m[1]}, valid: ${m[2]}`],
            [/^YAML解析错误: (.+)$/, (m) => `YAML parse error: ${m[1]}`],
            // Connection test
            [/^连接失败: (.+)$/, (m) => `Connection failed: ${m[1]}`],
        ],
        vi: [
            // Model count
            [/^共 (\d+) 个模型$/, (m) => `${m[1]} mô hình`],
            // Model group with count
            [/^其他（(\d+)）$/, (m) => `Khác (${m[1]})`],
            // Quote font size buttons
            [/^语录[：:](\d+) px$/, (m) => `Trích: ${m[1]} px`],
            [/^作者[：:](\d+) px$/, (m) => `Tác giả: ${m[1]} px`],
            // Font size prompt
            [/^请输入(语录|作者)字号\(px\)$/, (m) => `Nhập cỡ chữ ${m[1] === '语录' ? 'trích dẫn' : 'tác giả'} (px)`],
            // Token labels in stats
            [/^输入[：:]/, () => 'Nhập: '],
            [/^输出[：:]/, () => 'Xuất: '],
            [/^缓存[：:]/, () => 'Đệm: '],
            // System info
            [/^CPU 型号[：:](.*)$/, (m) => `Mẫu CPU: ${m[1]}`],
            [/^云厂商[：:](.*)$/, (m) => `Nhà cung cấp: ${m[1]}`],
            [/^系统版本[：:](.*)$/, (m) => `HĐH: ${m[1]}`],
            [/^(\d+) 核心 \| (.+)$/, (m) => `${m[1]} lõi | ${m[2]}`],
            // Uptime
            [/^(\d+)秒$/, (m) => `${m[1]} giây`],
            [/^(\d+)分钟$/, (m) => `${m[1]} phút`],
            [/^(\d+)小时(\d+)分$/, (m) => `${m[1]} giờ ${m[2]} phút`],
            [/^(\d+)天(\d+)小时$/, (m) => `${m[1]} ngày ${m[2]} giờ`],
            // Update history
            [/^上次更新: (.+)$/, (m) => {
                let t = m[1];
                t = t.replace('暂无记录', 'Chưa có');
                t = t.replace(/ 分钟前/, ' phút trước');
                t = t.replace(/ 小时前/, ' giờ trước');
                t = t.replace(/ 天前/, ' ngày trước');
                return `Cập nhật cuối: ${t}`;
            }],
            [/(\d+(?:\.\d+)?)\s*分钟前/, (m) => `${m[1]} phút trước`],
            [/(\d+(?:\.\d+)?)\s*小时前/, (m) => `${m[1]} giờ trước`],
            [/(\d+(?:\.\d+)?)\s*天前/, (m) => `${m[1]} ngày trước`],
            [/^历史: /, () => 'Lịch sử: '],
            // Update check
            [/^发现新版本: (.+)$/, (m) => `Phiên bản mới: ${m[1]}`],
            // Service actions
            [/^(启动|停止|重启)(成功|失败)$/, (m) => {
                const a = { '启动': 'Khởi động', '停止': 'Dừng', '重启': 'Khởi động lại' };
                const r = m[2] === '成功' ? 'thành công' : 'thất bại';
                return `${a[m[1]] || m[1]} ${r}`;
            }],
            // Error message prefixes
            [/^清空失败: (.+)$/, (m) => `Xóa thất bại: ${m[1]}`],
            [/^保存失败: (.+)$/, (m) => `Lưu thất bại: ${m[1]}`],
            [/^部分设置已保存: (.+)$/, (m) => `Lưu một phần: ${m[1]}`],
            [/^重载失败: (.+)$/, (m) => `Tải lại thất bại: ${m[1]}`],
            // Routing
            [/^路由策略已设置为 (.+)$/, (m) => `Định tuyến: ${m[1]}`],
            [/^无效的策略[，,]可选: (.+)$/, (m) => `Chiến lược không hợp lệ. Tùy chọn: ${m[1]}`],
            // Health check messages from backend
            [/^配置错误: (.+)$/, (m) => `Lỗi cấu hình: ${m[1]}`],
            [/^已使用 ([\d.]+)%$/, (m) => `Đã dùng ${m[1]}%`],
            [/^找到 (\d+) 个凭证文件$/, (m) => `Tìm thấy ${m[1]} tệp xác thực`],
            [/^端口 (\d+) (开放|关闭)$/, (m) => `Cổng ${m[1]} ${m[2] === '开放' ? 'mở' : 'đóng'}`],
            [/^端口 (\d+) 正常$/, (m) => `Cổng ${m[1]} OK`],
            // Config validation errors from backend
            [/^缺少必需字段: (.+)$/, (m) => `Thiếu trường bắt buộc: ${m[1]}`],
            [/^provider\[(\d+)\] 必须是一个对象$/, (m) => `provider[${m[1]}] phải là object`],
            [/^provider\[(\d+)\] 缺少(\w+)字段$/, (m) => `provider[${m[1]}] thiếu trường ${m[2]}`],
            [/^未知的路由策略: (.+)[，,]有效值: (.+)$/, (m) => `Chiến lược không rõ: ${m[1]}, hợp lệ: ${m[2]}`],
            [/^YAML解析错误: (.+)$/, (m) => `Lỗi phân tích YAML: ${m[1]}`],
            // Connection test
            [/^连接失败: (.+)$/, (m) => `Kết nối thất bại: ${m[1]}`],
        ]
    };

    // ==================== Core Translation Function ====================
    let currentLang = localStorage.getItem('lang') || 'zh';

    function t(text) {
        if (!text || currentLang === 'zh') return text;
        const s = text.trim();
        if (!s) return text;

        // Exact match
        if (T[s] && T[s][currentLang]) return T[s][currentLang];

        // Pattern match
        const patterns = PATTERNS[currentLang];
        if (patterns) {
            for (const [re, fn] of patterns) {
                const m = s.match(re);
                if (m) return fn(m);
            }
        }

        return text;
    }

    // Expose globally
    window.__i18n_t = t;
    window.__i18n_lang = () => currentLang;

    // ==================== DOM Translation ====================
    function translateTextNode(node) {
        if (!node.textContent) return;
        const original = node._i18nOriginal || node.textContent;
        node._i18nOriginal = original;
        node.textContent = t(original);
    }

    function translateElement(el) {
        if (!el || el.nodeType === Node.COMMENT_NODE) return;

        // Translate title attribute
        if (el.title) {
            el._i18nTitleOrig = el._i18nTitleOrig || el.title;
            el.title = t(el._i18nTitleOrig);
        }

        // Translate placeholder attribute
        if (el.placeholder) {
            el._i18nPhOrig = el._i18nPhOrig || el.placeholder;
            el.placeholder = t(el._i18nPhOrig);
        }

        // Translate direct text nodes only (skip elements with complex children like SVGs)
        for (const child of el.childNodes) {
            if (child.nodeType === Node.TEXT_NODE && child.textContent.trim()) {
                translateTextNode(child);
            }
        }
    }

    function translateAll() {
        // Title
        document.title = t('CPA-XX 管理面板');

        // All elements with text
        const selectors = [
            '.card-title', '.card-subtitle', '.info-label', '.info-value',
            '.stat-label', '.btn', '.badge', '.header-stat span:not(.header-stat-dot):not(.header-stat-value)',
            '.log-title', '.modal-title', '.health-name', '.health-pricing-title',
            '.req-summary-label', '.update-banner-text span',
            'option', 'label span', 'summary',
            '.log-entry .log-msg'
        ];
        document.querySelectorAll(selectors.join(',')).forEach(translateElement);

        // Placeholders on inputs
        document.querySelectorAll('input[placeholder]').forEach(el => {
            el._i18nPhOrig = el._i18nPhOrig || el.placeholder;
            el.placeholder = t(el._i18nPhOrig);
        });

        // Textarea placeholder
        document.querySelectorAll('textarea[placeholder]').forEach(el => {
            el._i18nPhOrig = el._i18nPhOrig || el.placeholder;
            el.placeholder = t(el._i18nPhOrig);
        });

        // Title attributes
        document.querySelectorAll('[title]').forEach(el => {
            if (!el.title) return;
            el._i18nTitleOrig = el._i18nTitleOrig || el.title;
            el.title = t(el._i18nTitleOrig);
        });
    }

    // ==================== Monkey-patch JS functions ====================
    function patchGlobalFunctions() {
        // Patch toast()
        if (typeof window.toast === 'function') {
            const origToast = window.toast;
            window.toast = function (msg, type) {
                return origToast.call(this, t(msg), type);
            };
        }

        // Patch confirm()
        const origConfirm = window.confirm;
        window.confirm = function (msg) {
            return origConfirm.call(this, t(msg));
        };

        // Patch prompt()
        const origPrompt = window.prompt;
        window.prompt = function (msg, defaultVal) {
            return origPrompt.call(this, t(msg), defaultVal);
        };

        // Patch formatMillionTokens to use translated unit
        if (typeof window.formatMillionTokens === 'function') {
            window.formatMillionTokens = function (value) {
                const num = Number(value || 0);
                const formatted = (num / 1000000).toFixed(2);
                const unit = t('百万Tokens');
                return `<span class="req-token-number">${formatted}</span>&nbsp;&nbsp;<span class="req-token-unit">${unit}</span>`;
            };
        }

        // Patch formatUsd to use translated unit
        if (typeof window.formatUsd === 'function') {
            window.formatUsd = function (value) {
                const num = Number(value || 0);
                const formatted = num.toFixed(2);
                const unit = t('美元');
                return `<span class="req-cost-number">${formatted}</span>&nbsp;<span class="req-cost-unit">${unit}</span>`;
            };
        }

        // Patch updateQuoteFontButtons
        if (typeof window.updateQuoteFontButtons === 'function') {
            const origQFB = window.updateQuoteFontButtons;
            window.updateQuoteFontButtons = function () {
                origQFB.call(this);
                const textBtn = document.getElementById('quote-size-btn');
                const authorBtn = document.getElementById('quote-author-size-btn');
                if (textBtn) textBtn.textContent = t(textBtn.textContent);
                if (authorBtn) authorBtn.textContent = t(authorBtn.textContent);
            };
        }
    }

    // ==================== MutationObserver for dynamic content ====================
    let observerActive = false;

    function setupObserver() {
        if (currentLang === 'zh' || observerActive) return;
        observerActive = true;

        const observer = new MutationObserver((mutations) => {
            for (const mutation of mutations) {
                if (mutation.type === 'childList') {
                    for (const node of mutation.addedNodes) {
                        if (node.nodeType === Node.TEXT_NODE && node.textContent.trim()) {
                            translateTextNode(node);
                        } else if (node.nodeType === Node.ELEMENT_NODE) {
                            translateElement(node);
                            node.querySelectorAll && node.querySelectorAll('*').forEach(translateElement);
                        }
                    }
                } else if (mutation.type === 'characterData' && mutation.target.nodeType === Node.TEXT_NODE) {
                    const text = mutation.target.textContent.trim();
                    if (text && t(text) !== text) {
                        mutation.target._i18nOriginal = text;
                        mutation.target.textContent = t(text);
                    }
                }
            }
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true,
            characterData: true,
        });
    }

    // ==================== Language Switcher UI ====================
    function createLanguageSwitcher() {
        const headerActions = document.querySelector('.header-actions');
        if (!headerActions) return;

        const select = document.createElement('select');
        select.className = 'input';
        select.id = 'lang-switcher';
        select.style.cssText = 'width:auto;padding:4px 6px;font-size:11px;border-radius:8px;cursor:pointer;background:var(--glass-bg);color:var(--text-primary);border:1px solid var(--glass-border);backdrop-filter:var(--blur);';

        const langs = [
            { code: 'zh', label: '中文' },
            { code: 'en', label: 'English' },
            { code: 'vi', label: 'Tiếng Việt' },
        ];

        langs.forEach(l => {
            const opt = document.createElement('option');
            opt.value = l.code;
            opt.textContent = l.label;
            if (l.code === currentLang) opt.selected = true;
            select.appendChild(opt);
        });

        select.addEventListener('change', () => {
            currentLang = select.value;
            localStorage.setItem('lang', currentLang);
            if (currentLang === 'zh') {
                // Restore originals
                document.querySelectorAll('*').forEach(el => {
                    if (el._i18nTitleOrig) el.title = el._i18nTitleOrig;
                    if (el._i18nPhOrig) el.placeholder = el._i18nPhOrig;
                    for (const child of el.childNodes) {
                        if (child.nodeType === Node.TEXT_NODE && child._i18nOriginal) {
                            child.textContent = child._i18nOriginal;
                        }
                    }
                });
                document.title = 'CPA-XX 管理面板';
            } else {
                translateAll();
                setupObserver();
            }
            // Re-trigger data refresh to translate dynamic content
            if (typeof window.refreshStatus === 'function') window.refreshStatus();
            if (typeof window.refreshResources === 'function') window.refreshResources();
            if (typeof window.updateQuoteFontButtons === 'function') window.updateQuoteFontButtons();
        });

        headerActions.insertBefore(select, headerActions.firstChild);
    }

    // ==================== Init ====================
    function init() {
        createLanguageSwitcher();
        patchGlobalFunctions();
        if (currentLang !== 'zh') {
            translateAll();
            setupObserver();
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
