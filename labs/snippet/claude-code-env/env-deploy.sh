#!/bin/bash

# Claude Code Environment Setup Script
# Author: Claude Assistant
# Purpose: Automatically configure environment variables for Claude Code on macOS and Linux

set -e  # Exit on error

# Colors for output
RED='\033[1;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Function to display current environment variables
display_current_env() {
    print_info "当前环境变量状态："
    echo -e "${BLUE}----------------------------------------${NC}"
    
    # Get current shell type for proper variable display
    CURRENT_SHELL=$(basename "$SHELL")
    
    if [[ "$CURRENT_SHELL" == "fish" ]]; then
        # Fish shell syntax
        echo "ANTHROPIC_BASE_URL=$(set -q ANTHROPIC_BASE_URL && echo $ANTHROPIC_BASE_URL || echo '(未设置)')"
    else
        # Bash/Zsh syntax
        if [ -n "$ANTHROPIC_BASE_URL" ]; then
            echo "ANTHROPIC_BASE_URL=$ANTHROPIC_BASE_URL"
        else
            echo "ANTHROPIC_BASE_URL=(未设置)"
        fi
    fi
    
    echo -e "${BLUE}----------------------------------------${NC}"
}

# Header
echo -e "\n${BLUE}========================================${NC}"
echo -e "${BLUE}Claude Code Environment Setup${NC}"
echo -e "${BLUE}========================================${NC}\n"

# Display current environment variables before any changes
display_current_env
echo

# Function to validate provider URL format
validate_provider_url() {
    local url="$1"
    
    # Check if URL is empty
    if [ -z "$url" ]; then
        print_error "Provider URL 不能为空"
        return 1
    fi
    
    # Check if URL starts with http:// or https://
    if [[ ! "$url" =~ ^https?:// ]]; then
        print_error "Provider URL 必须以 http:// 或 https:// 开头"
        print_error "当前URL: $url"
        return 1
    fi
    
    # Remove trailing slashes for consistency
    url="${url%/}"
    
    # Check if URL ends with /v1/chat/completions (and remove it if present)
    if [[ "$url" =~ /v1/chat/completions$ ]]; then
        print_warning "检测到URL已包含 /v1/chat/completions 后缀"
        url="${url%/v1/chat/completions}"
        print_info "将使用基础URL: $url"
        print_info "最终URL将为: $url/v1/chat/completions"
    fi
    
    # Basic URL format validation (check for valid domain pattern)
    if [[ ! "$url" =~ ^https?://[a-zA-Z0-9.-]+([0-9]+)?(/.*)?$ ]]; then
        print_error "Provider URL 格式不正确"
        print_error "当前URL: $url"
        print_error "正确格式示例: https://api.example.com 或 http://localhost:8000"
        return 1
    fi
    
    # Set the cleaned URL back to the global variable
    PROVIDER_URL="$url"
    print_success "Provider URL 格式验证通过: $PROVIDER_URL"
    return 0
}

# Check if both API key and provider URL are provided as arguments
if [ $# -lt 2 ]; then
    print_error "请提供API密钥和提供商URL作为参数"
    echo "使用方法: $0 <your-api-key> <provider-url>"
    echo "  your-api-key: 必需的API密钥"
    echo "  provider-url: 必需的提供商URL（将自动添加 /v1/chat/completions 后缀）"
    exit 1
fi

ANTHROPIC_API_KEY="$1"
PROVIDER_URL="$2"  # 第二个参数为必需的 provider URL
ANTHROPIC_BASE_URL="http://127.0.0.1:3456"

# Validate provider URL format
if ! validate_provider_url "$PROVIDER_URL"; then
    print_error "Provider URL 验证失败，请检查URL格式"
    echo ""
    echo "正确的使用示例："
    echo "  $0 sk-ant-1234567890 https://api.example.com"
    echo "  $0 sk-ant-1234567890 http://localhost:8000"
    echo "  $0 sk-ant-1234567890 https://339fe73e.r11.vip.cpolar.cn"
    echo ""
    echo "注意："
    echo "  - URL必须以 http:// 或 https:// 开头"
    echo "  - 不需要手动添加 /v1/chat/completions 后缀，脚本会自动添加"
    echo "  - 如果URL已包含该后缀，脚本会自动检测并处理"
    exit 1
fi

# Detect OS and shell
detect_os_and_shell() {
    print_info "检测操作系统和Shell环境..."
    
    # Detect OS
    if [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macOS"
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        OS="Linux"
    else
        print_error "不支持的操作系统: $OSTYPE"
        exit 1
    fi
    
    # Detect Shell
    CURRENT_SHELL=$(basename "$SHELL")
    
    # Determine config file based on shell
    case "$CURRENT_SHELL" in
        bash)
            if [[ "$OS" == "macOS" ]]; then
                CONFIG_FILE="$HOME/.bash_profile"
            else
                CONFIG_FILE="$HOME/.bashrc"
            fi
            ;;
        zsh)
            CONFIG_FILE="$HOME/.zshrc"
            ;;
        fish)
            CONFIG_FILE="$HOME/.config/fish/config.fish"
            ;;
        *)
            print_error "不支持的Shell: $CURRENT_SHELL"
            exit 1
            ;;
    esac
    
    print_success "检测完成 - 系统: $OS, Shell: $CURRENT_SHELL"
    print_info "配置文件: $CONFIG_FILE"
}

# Function to add environment variables to config file
add_env_vars() {
    print_info "开始配置环境变量..."
    
    # Create backup
    if [ -f "$CONFIG_FILE" ]; then
        cp "$CONFIG_FILE" "$CONFIG_FILE.backup.$(date +%Y%m%d_%H%M%S)"
        print_info "已备份原配置文件"
    fi
    
    # Check if variables already exist
    if grep -q "ANTHROPIC_BASE_URL" "$CONFIG_FILE" 2>/dev/null; then
        print_warning "检测到已存在的Claude Code环境变量配置"
        print_info "正在清理所有现有配置..."
        
        # Remove ALL existing ANTHROPIC environment variable configurations
        # For bash/zsh: export VARIABLE=...
        # For fish: set -x VARIABLE ...
        if [[ "$CURRENT_SHELL" == "fish" ]]; then
            # Fish shell: remove 'set -x VARIABLE ...' patterns
            # Using -E for extended regex on macOS/BSD sed
            sed -i.tmp -E '/^[[:space:]]*set[[:space:]]+-x[[:space:]]+ANTHROPIC_BASE_URL/d' "$CONFIG_FILE" 2>/dev/null || true
        else
            # Bash/Zsh: remove 'export VARIABLE=...' patterns
            # Using -E for extended regex on macOS/BSD sed
            sed -i.tmp -E '/^[[:space:]]*export[[:space:]]+ANTHROPIC_BASE_URL=/d' "$CONFIG_FILE" 2>/dev/null || true
        fi
        
        # Also remove the marked sections for backward compatibility
        sed -i.tmp '/# Claude Code Environment Variables/,/# End Claude Code Environment Variables/d' "$CONFIG_FILE" 2>/dev/null || true
        
        # Clean up temporary files
        rm -f "$CONFIG_FILE.tmp"
        
        print_success "已彻底清理所有旧配置，准备写入新配置"
    fi
    
    # Add environment variables based on shell type
    if [[ "$CURRENT_SHELL" == "fish" ]]; then
        cat >> "$CONFIG_FILE" << EOF

# Claude Code Environment Variables
set -x ANTHROPIC_BASE_URL "$ANTHROPIC_BASE_URL"
# End Claude Code Environment Variables
EOF
    else
        cat >> "$CONFIG_FILE" << EOF

# Claude Code Environment Variables
export ANTHROPIC_BASE_URL="$ANTHROPIC_BASE_URL"
# End Claude Code Environment Variables
EOF
    fi
    
    print_success "环境变量已写入配置文件"
}

# Function to update .claude.json
update_claude_json() {
    print_info "更新 ~/.claude.json 配置..."
    
    # Check if jq is installed
    if ! command -v jq &> /dev/null; then
        print_error "需要安装 jq 工具"
        if [[ "$OS" == "macOS" ]]; then
            print_info "请运行: brew install jq"
        else
            print_info "请运行: sudo apt-get install jq (Ubuntu/Debian) 或 sudo yum install jq (CentOS/RHEL)"
        fi
        return 1
    fi
    
    # Execute the jq command
    print_info "添加API密钥到Claude配置..."
    
    # Get the last 20 characters of the API key
    KEY_SUFFIX="${ANTHROPIC_API_KEY: -20}"
    
    # Create .claude.json if it doesn't exist
    if [ ! -f "$HOME/.claude.json" ]; then
        echo '{}' > "$HOME/.claude.json"
        print_info "创建新的 ~/.claude.json 文件"
    fi
    
    # Update the JSON file
    if (cat ~/.claude.json 2>/dev/null || echo 'null') | jq --arg key "$KEY_SUFFIX" '(. // {}) | .customApiKeyResponses.approved |= ([.[]?, $key] | unique)' > ~/.claude.json.tmp; then
        mv ~/.claude.json.tmp ~/.claude.json
        print_success "Claude配置已更新"
        
        # Display the updated customApiKeyResponses
        print_info "更新后的 customApiKeyResponses 内容:"
        echo -e "${BLUE}----------------------------------------${NC}"
        jq '.customApiKeyResponses' ~/.claude.json 2>/dev/null || echo "{}"
        echo -e "${BLUE}----------------------------------------${NC}"
    else
        print_error "更新Claude配置失败"
        rm -f ~/.claude.json.tmp
        return 1
    fi
}

# Function to source the config file
activate_config() {
    print_info "激活配置..."
    
    # Export variables for current session
    export ANTHROPIC_BASE_URL="$ANTHROPIC_BASE_URL"
    
    print_success "环境变量已在当前会话中激活"
    print_info "要在新的终端会话中使用，请运行以下命令："
    
    if [[ "$CURRENT_SHELL" == "fish" ]]; then
        echo -e "${GREEN}source $CONFIG_FILE${NC}"
    else
        echo -e "${GREEN}source $CONFIG_FILE${NC}"
    fi
    
    print_info "或者重新打开终端窗口"
}

# Function to verify configuration
verify_config() {
    print_info "验证配置..."
    
    # Check if variables are set
    if [ -n "$ANTHROPIC_BASE_URL" ]; then
        print_success "环境变量验证成功"
        echo "ANTHROPIC_BASE_URL: $ANTHROPIC_BASE_URL"
    else
        print_error "环境变量验证失败"
        return 1
    fi
    
    # Check .claude.json
    if [ -f "$HOME/.claude.json" ]; then
        if jq -e '.customApiKeyResponses.approved' "$HOME/.claude.json" &>/dev/null; then
            print_success "Claude配置文件验证成功"
        else
            print_warning "Claude配置文件存在但可能不完整"
        fi
    else
        print_error "Claude配置文件不存在"
    fi
}

# Function to configure Claude Code settings
configure_claude_code_settings() {
    print_info "配置 Claude Code settings.json..."
    
    # Create the .claude directory if it doesn't exist
    local claude_settings_dir="$HOME/.claude"
    if [ ! -d "$claude_settings_dir" ]; then
        mkdir -p "$claude_settings_dir"
        print_info "创建配置目录: $claude_settings_dir"
    else
        print_info "配置目录已存在: $claude_settings_dir"
    fi
    
    local settings_file="$claude_settings_dir/settings.json"
    
    # Backup existing settings if they exist
    if [ -f "$settings_file" ]; then
        local backup_file="$settings_file.backup.$(date +%Y%m%d_%H%M%S)"
        cp "$settings_file" "$backup_file"
        print_info "已备份现有的 Claude Code settings.json 文件到: $backup_file"
    fi
    
    # Create the settings.json file with the required configuration
    cat > "$settings_file" << EOF
{
    "env": {
        "ANTHROPIC_AUTH_TOKEN": "test",
        "ANTHROPIC_API_KEY": "custom-api-key",
        "ANTHROPIC_BASE_URL": "$ANTHROPIC_BASE_URL"
    }
}
EOF
    
    if [ $? -eq 0 ]; then
        print_success "Claude Code settings.json 已创建/更新: $settings_file"
        
        # Verify file was created and display file info
        if [ -f "$settings_file" ]; then
            local file_size=$(stat -c%s "$settings_file" 2>/dev/null || echo "未知")
            print_info "文件信息: 大小 ${file_size} bytes"
            print_info "文件权限: $(stat -c%A "$settings_file" 2>/dev/null || echo "未知")"
        fi
        
        # Display the settings content
        print_info "当前 Claude Code settings.json 内容:"
        echo -e "${BLUE}----------------------------------------${NC}"
        if [ -f "$settings_file" ]; then
            cat "$settings_file" 2>/dev/null || echo "无法读取配置文件"
        else
            echo "配置文件不存在"
        fi
        echo -e "${BLUE}----------------------------------------${NC}"
    else
        print_error "创建 Claude Code settings.json 失败"
        print_error "请检查目录权限: $claude_settings_dir"
        return 1
    fi
}

# Function to configure Claude Code Router
configure_claude_code_router() {
    print_info "配置 Claude Code Router..."
    
    # Create the .claude-code-router directory if it doesn't exist
    local ccr_config_dir="$HOME/.claude-code-router"
    if [ ! -d "$ccr_config_dir" ]; then
        mkdir -p "$ccr_config_dir"
        print_info "创建配置目录: $ccr_config_dir"
    fi
    
    # Source config file path (in the same directory as this script)
    local script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    local source_config="$script_dir/claude-code-router-config.json"
    local target_config="$ccr_config_dir/config.json"
    
    # Check if source config file exists
    if [ ! -f "$source_config" ]; then
        print_error "源配置文件不存在: $source_config"
        print_error "请先创建 config.json 文件并配置相关内容"
        return 1
    fi
    
    # Check if jq is available for JSON processing
    if ! command -v jq &> /dev/null; then
        print_error "需要安装 jq 工具来处理 JSON 配置文件"
        if [[ "$OS" == "macOS" ]]; then
            print_info "请运行: brew install jq"
        else
            print_info "请运行: sudo apt-get install jq (Ubuntu/Debian) 或 sudo yum install jq (CentOS/RHEL)"
        fi
        return 1
    fi
    
    # Validate that API key and provider URL were provided
    if [ -z "$ANTHROPIC_API_KEY" ]; then
        print_error "未提供 API key，无法配置 Claude Code Router"
        print_error "请在运行脚本时提供 API key 作为参数"
        return 1
    fi
    
    if [ -z "$PROVIDER_URL" ]; then
        print_error "未提供 Provider URL，无法配置 Claude Code Router"
        print_error "请在运行脚本时提供 Provider URL 作为第二个参数"
        return 1
    fi
    
    # Create a temporary config file with the API key and provider URL replaced
    local temp_config="$source_config.tmp"
    # Update both api_key and api_base_url with the provider URL
    if jq --arg api_key "$ANTHROPIC_API_KEY" --arg provider_url "$PROVIDER_URL/v1/chat/completions" \
       '.Providers[0].api_key = $api_key | .Providers[0].api_base_url = $provider_url' \
       "$source_config" > "$temp_config"; then
        print_success "已将 API key 和 Provider URL 插入到配置中"
        print_info "Provider URL 设置为: $PROVIDER_URL/v1/chat/completions"
    else
        print_error "配置文件 JSON 格式错误或无法处理"
        rm -f "$temp_config"
        return 1
    fi
    
    # Backup existing config if it exists
    if [ -f "$target_config" ]; then
        cp "$target_config" "$target_config.backup.$(date +%Y%m%d_%H%M%S)"
        print_info "已备份现有的 CCR 配置文件"
    fi
    
    # Copy the processed config file to CCR directory
    if cp "$temp_config" "$target_config"; then
        print_success "配置文件已复制到: $target_config"
        
        # Clean up temporary file
        rm -f "$temp_config"
        
        # Display the config content (mask the API key for security)
        print_info "当前 CCR 配置内容:"
        echo -e "${BLUE}----------------------------------------${NC}"
        # Show masked API key and provider URL
        if jq --arg masked_key "****${ANTHROPIC_API_KEY: -4}" --arg provider_url "$PROVIDER_URL/v1/chat/completions" \
           '.Providers[0].api_key = $masked_key | .Providers[0].api_base_url = $provider_url' "$target_config" 2>/dev/null; then
            true
        else
            echo "无法读取配置文件"
        fi
        echo -e "${BLUE}----------------------------------------${NC}"
    else
        print_error "配置文件复制失败"
        rm -f "$temp_config"
        return 1
    fi
}

# Function to add ~/.local/bin to PATH
add_local_bin_to_path() {
    local npm_bin_path="$HOME/.local/bin"
    
    # Check if ~/.local/bin is already in PATH
    if [[ ":$PATH:" == *":$npm_bin_path:"* ]]; then
        print_info "~/.local/bin 已在 PATH 中"
        return 0
    fi
    
    print_info "添加 ~/.local/bin 到 PATH..."
    
    # Add to shell configuration file
    if [[ "$CURRENT_SHELL" == "fish" ]]; then
        # Fish shell: Check if PATH entry already exists in config
        if ! grep -q "set -x PATH.*$HOME/.local/bin" "$CONFIG_FILE" 2>/dev/null; then
            echo "# Add local npm bin to PATH" >> "$CONFIG_FILE"
            echo "set -x PATH \"$HOME/.local/bin\" \$PATH" >> "$CONFIG_FILE"
            print_success "已添加 ~/.local/bin 到 Fish 配置文件"
        fi
    else
        # Bash/Zsh: Check if PATH entry already exists in config
        if ! grep -q "export PATH.*$HOME/.local/bin" "$CONFIG_FILE" 2>/dev/null; then
            echo "# Add local npm bin to PATH" >> "$CONFIG_FILE"
            echo "export PATH=\"$HOME/.local/bin:\$PATH\"" >> "$CONFIG_FILE"
            print_success "已添加 ~/.local/bin 到 Bash/Zsh 配置文件"
        fi
    fi
    
    # Export for current session
    export PATH="$npm_bin_path:$PATH"
    print_success "~/.local/bin 已添加到当前会话的 PATH"
}

# Function to install npm packages
install_npm_packages() {
    print_info "安装 Claude Code 相关包..."
    
    # Check if npm is available
    if ! command -v npm &> /dev/null; then
        print_error "npm 未找到，请先安装 Node.js 环境"
        print_info "可以运行 env-install.sh 脚本来安装 Node.js 环境"
        return 1
    fi
    
    print_info "当前 npm 版本: $(npm --version)"
    print_info "当前 Node.js 版本: $(node --version)"
    
    # Track if local installation was used
    local local_install_used=false
    
    # Step 1: Install Claude Code first (required for Claude Code Router)
    print_info "第一步：安装 @anthropic-ai/claude-code..."
    if npm install -g @anthropic-ai/claude-code; then
        print_success "Claude Code 安装成功"
    else
        print_error "Claude Code 全局安装失败"
        print_info "尝试使用本地权限安装..."
        if npm install --prefix ~/.local @anthropic-ai/claude-code; then
            print_success "Claude Code 本地安装成功"
            local_install_used=true
        else
            print_error "Claude Code 安装失败，请检查网络连接或权限"
            return 1
        fi
    fi
    
    # Step 2: Install Claude Code Router (requires Claude Code to be installed first)
    print_info "第二步：安装 @musistudio/claude-code-router..."
    if npm install -g @musistudio/claude-code-router; then
        print_success "Claude Code Router 安装成功"
    else
        print_error "Claude Code Router 全局安装失败"
        print_info "尝试使用本地权限安装..."
        if npm install --prefix ~/.local @musistudio/claude-code-router; then
            print_success "Claude Code Router 本地安装成功"
            local_install_used=true
        else
            print_error "Claude Code Router 安装失败，请检查网络连接或权限"
            return 1
        fi
    fi
    
    # Add ~/.local/bin to PATH if local installation was used
    if [ "$local_install_used" = true ]; then
        print_info "检测到本地安装，添加 ~/.local/bin 到 PATH..."
        add_local_bin_to_path
    fi
    
    # Verify installations
    print_info "验证安装结果..."
    
    # Check Claude Code (实际可执行文件名是 claude)
    if command -v claude &> /dev/null || [ -f "$HOME/.local/bin/claude" ]; then
        print_success "@anthropic-ai/claude-code 验证成功"
        # Try to get version if possible
        if command -v claude &> /dev/null; then
            local claude_version=$(claude --version 2>/dev/null || echo "版本信息不可用")
            print_info "Claude Code 版本: $claude_version"
        elif [ -f "$HOME/.local/bin/claude" ]; then
            local claude_version=$("$HOME/.local/bin/claude" --version 2>/dev/null || echo "版本信息不可用")
            print_info "Claude Code 版本: $claude_version"
            print_info "使用方法: ~/.local/bin/claude 或重新加载终端后使用 claude"
        fi
    else
        print_warning "@anthropic-ai/claude-code 验证失败，可能需要重新加载终端"
    fi
    
    # Check Claude Code Router (实际可执行文件名是 ccr)
    if command -v ccr &> /dev/null || [ -f "$HOME/.local/bin/ccr" ]; then
        print_success "@musistudio/claude-code-router 验证成功"
        # Try to get version if possible
        if command -v ccr &> /dev/null; then
            local router_version=$(ccr --version 2>/dev/null || echo "版本信息不可用")
            print_info "Claude Code Router 版本: $router_version"
        elif [ -f "$HOME/.local/bin/ccr" ]; then
            local router_version=$("$HOME/.local/bin/ccr" --version 2>/dev/null || echo "版本信息不可用")
            print_info "Claude Code Router 版本: $router_version"
            print_info "使用方法: ~/.local/bin/ccr 或重新加载终端后使用 ccr"
        fi
    else
        print_warning "@musistudio/claude-code-router 验证失败，可能需要重新加载终端"
    fi
    
    print_success "npm 包安装完成"
}

# Function to start Claude Code Router service
start_ccr_service() {
    print_info "启动 Claude Code Router 服务..."
    
    # Check if ccr command is available
    local ccr_cmd=""
    if command -v ccr &> /dev/null; then
        ccr_cmd="ccr"
    elif [ -f "$HOME/.local/bin/ccr" ]; then
        ccr_cmd="$HOME/.local/bin/ccr"
    else
        # Check npm global installation
        if command -v npm &> /dev/null; then
            local npm_global_path=$(npm config get prefix 2>/dev/null)
            if [ -n "$npm_global_path" ] && [ -f "$npm_global_path/bin/ccr" ]; then
                ccr_cmd="$npm_global_path/bin/ccr"
            # Check npm local installation
            elif [ -f "$HOME/.local/lib/node_modules/@musistudio/claude-code-router/bin/ccr.js" ]; then
                ccr_cmd="node $HOME/.local/lib/node_modules/@musistudio/claude-code-router/bin/ccr.js"
            fi
        fi
    fi
    
    if [ -z "$ccr_cmd" ]; then
        print_error "无法找到 ccr 命令，请确认 Claude Code Router 已正确安装"
        print_info "您可以手动运行以下命令来启动服务："
        print_info "  ccr start"
        return 1
    fi
    
    print_info "使用命令: $ccr_cmd"
    
    # Try to start ccr
    print_info "尝试启动 Claude Code Router..."
    if $ccr_cmd restart 2>/dev/null; then
        print_success "Claude Code Router 启动成功"
        
        # Wait a moment and check if it's running
        sleep 2
        if $ccr_cmd status &>/dev/null; then
            print_success "Claude Code Router 服务运行正常"
        else
            print_warning "Claude Code Router 可能未正常运行，请手动检查"
        fi
    else
        print_warning "Claude Code Router 启动失败，尝试重启..."
        
        # Try to restart ccr
        if $ccr_cmd restart 2>/dev/null; then
            print_success "Claude Code Router 重启成功"
            
            # Wait a moment and check if it's running
            sleep 2
            if $ccr_cmd status &>/dev/null; then
                print_success "Claude Code Router 服务运行正常"
            else
                print_warning "Claude Code Router 可能未正常运行"
            fi
        else
            print_error "Claude Code Router 重启也失败"
            print_info "请手动运行以下命令："
            print_info "  $ccr_cmd start"
            print_info "或："
            print_info "  $ccr_cmd restart"
            
            # Show potential issues
            echo -e "${YELLOW}可能的问题:${NC}"
            echo -e "1. 端口被占用 (默认端口 3456)"
            echo -e "2. 配置文件有误"
            echo -e "3. 权限问题"
            echo -e "4. Node.js 环境问题"
            echo ""
            echo -e "${BLUE}调试命令:${NC}"
            echo -e "  $ccr_cmd --help     # 查看帮助"
            echo -e "  $ccr_cmd status     # 查看状态"
            echo -e "  $ccr_cmd logs       # 查看日志"
            echo -e "  netstat -an | grep 3456  # 检查端口占用"
            
            return 1
        fi
    fi
    
    print_info "Claude Code Router 现在应该在 http://127.0.0.1:3456 运行"
}

# Function to display version and installation path information
print_version_and_path_info() {
    print_info "显示 Claude Code 版本信息和安装路径..."
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}Claude Code 安装信息${NC}"
    echo -e "${BLUE}========================================${NC}"
    
    # Check Claude Code installation and version
    local claude_code_path=""
    local claude_code_version=""
    local claude_code_status="❌ 未安装"
    
    # Try multiple detection methods for Claude Code (实际可执行文件名是 claude)
    if command -v claude &> /dev/null; then
        claude_code_path=$(which claude)
        claude_code_version=$(claude --version 2>/dev/null || echo "版本信息不可用")
        claude_code_status="✅ 已安装 (全局)"
    elif [ -f "$HOME/.local/bin/claude" ]; then
        claude_code_path="$HOME/.local/bin/claude"
        claude_code_version=$("$HOME/.local/bin/claude" --version 2>/dev/null || echo "版本信息不可用")
        claude_code_status="✅ 已安装 (本地)"
    else
        # Check npm global packages
        if command -v npm &> /dev/null; then
            local npm_global_path=$(npm config get prefix 2>/dev/null)
            if [ -n "$npm_global_path" ] && [ -f "$npm_global_path/bin/claude" ]; then
                claude_code_path="$npm_global_path/bin/claude"
                claude_code_version=$("$npm_global_path/bin/claude" --version 2>/dev/null || echo "版本信息不可用")
                claude_code_status="✅ 已安装 (npm全局)"
            # Check npm local installation in ~/.local
            elif [ -f "$HOME/.local/lib/node_modules/@anthropic-ai/claude-code/bin/claude.js" ]; then
                claude_code_path="$HOME/.local/lib/node_modules/@anthropic-ai/claude-code/bin/claude.js"
                claude_code_version=$(node "$claude_code_path" --version 2>/dev/null || echo "版本信息不可用")
                claude_code_status="✅ 已安装 (npm本地)"
            else
                claude_code_path="未找到"
                claude_code_version="未安装"
            fi
        else
            claude_code_path="未找到"
            claude_code_version="未安装"
        fi
    fi
    
    # Check Claude Code Router installation and version
    local router_path=""
    local router_version=""
    local router_status="❌ 未安装"
    
    # Try multiple detection methods for Claude Code Router (实际可执行文件名是 ccr)
    if command -v ccr &> /dev/null; then
        router_path=$(which ccr)
        router_version=$(ccr --version 2>/dev/null || echo "版本信息不可用")
        router_status="✅ 已安装 (全局)"
    elif [ -f "$HOME/.local/bin/ccr" ]; then
        router_path="$HOME/.local/bin/ccr"
        router_version=$("$HOME/.local/bin/ccr" --version 2>/dev/null || echo "版本信息不可用")
        router_status="✅ 已安装 (本地)"
    else
        # Check npm global packages
        if command -v npm &> /dev/null; then
            local npm_global_path=$(npm config get prefix 2>/dev/null)
            if [ -n "$npm_global_path" ] && [ -f "$npm_global_path/bin/ccr" ]; then
                router_path="$npm_global_path/bin/ccr"
                router_version=$("$npm_global_path/bin/ccr" --version 2>/dev/null || echo "版本信息不可用")
                router_status="✅ 已安装 (npm全局)"
            # Check npm local installation in ~/.local
            elif [ -f "$HOME/.local/lib/node_modules/@musistudio/claude-code-router/bin/ccr.js" ]; then
                router_path="$HOME/.local/lib/node_modules/@musistudio/claude-code-router/bin/ccr.js"
                router_version=$(node "$router_path" --version 2>/dev/null || echo "版本信息不可用")
                router_status="✅ 已安装 (npm本地)"
            else
                router_path="未找到"
                router_version="未安装"
            fi
        else
            router_path="未找到"
            router_version="未安装"
        fi
    fi
    
    # Display information
    echo -e "${GREEN}Claude Code CLI:${NC}"
    echo -e "  状态: $claude_code_status"
    echo -e "  版本: ${YELLOW}$claude_code_version${NC}"
    echo -e "  路径: ${YELLOW}$claude_code_path${NC}"
    echo ""
    
    echo -e "${GREEN}Claude Code Router:${NC}"
    echo -e "  状态: $router_status"
    echo -e "  版本: ${YELLOW}$router_version${NC}"
    echo -e "  路径: ${YELLOW}$router_path${NC}"
    echo ""
    
    # Check npm packages installation status using npm list
    if command -v npm &> /dev/null; then
        echo -e "${GREEN}npm 包安装检查:${NC}"
        
        # Check global installations
        local global_claude=$(npm list -g @anthropic-ai/claude-code --depth=0 2>/dev/null | grep @anthropic-ai/claude-code || echo "未安装")
        local global_router=$(npm list -g @musistudio/claude-code-router --depth=0 2>/dev/null | grep @musistudio/claude-code-router || echo "未安装")
        
        echo -e "  全局安装:"
        if [[ "$global_claude" != "未安装" ]]; then
            echo -e "    ✅ @anthropic-ai/claude-code: ${YELLOW}$(echo "$global_claude" | grep -o '@[^[:space:]]*')${NC}"
        else
            echo -e "    ❌ @anthropic-ai/claude-code: ${YELLOW}未安装${NC}"
        fi
        
        if [[ "$global_router" != "未安装" ]]; then
            echo -e "    ✅ @musistudio/claude-code-router: ${YELLOW}$(echo "$global_router" | grep -o '@[^[:space:]]*')${NC}"
        else
            echo -e "    ❌ @musistudio/claude-code-router: ${YELLOW}未安装${NC}"
        fi
        
        # Check local installations
        if [ -d "$HOME/.local/lib/node_modules" ]; then
            echo -e "  本地安装 (~/.local):"
            if [ -d "$HOME/.local/lib/node_modules/@anthropic-ai/claude-code" ]; then
                local local_claude_version=$(cat "$HOME/.local/lib/node_modules/@anthropic-ai/claude-code/package.json" 2>/dev/null | grep '"version"' | cut -d'"' -f4 || echo "未知版本")
                echo -e "    ✅ @anthropic-ai/claude-code: ${YELLOW}$local_claude_version${NC}"
            else
                echo -e "    ❌ @anthropic-ai/claude-code: ${YELLOW}未安装${NC}"
            fi
            
            if [ -d "$HOME/.local/lib/node_modules/@musistudio/claude-code-router" ]; then
                local local_router_version=$(cat "$HOME/.local/lib/node_modules/@musistudio/claude-code-router/package.json" 2>/dev/null | grep '"version"' | cut -d'"' -f4 || echo "未知版本")
                echo -e "    ✅ @musistudio/claude-code-router: ${YELLOW}$local_router_version${NC}"
            else
                echo -e "    ❌ @musistudio/claude-code-router: ${YELLOW}未安装${NC}"
            fi
        fi
        echo ""
    fi
    
    # Display Node.js and npm versions for reference
    if command -v node &> /dev/null && command -v npm &> /dev/null; then
        echo -e "${GREEN}运行环境:${NC}"
        echo -e "  Node.js: ${YELLOW}$(node --version)${NC}"
        echo -e "  npm: ${YELLOW}$(npm --version)${NC}"
        echo ""
    fi
    
    # Display global npm packages location if available
    if command -v npm &> /dev/null; then
        local npm_global_path=$(npm config get prefix 2>/dev/null || echo "未知")
        echo -e "${GREEN}npm 配置:${NC}"
        echo -e "  全局安装路径: ${YELLOW}$npm_global_path${NC}"
        echo ""
    fi
    
    # Check Claude Code configuration files
    echo -e "${GREEN}Claude Code 配置文件:${NC}"
    
    # Check ~/.claude/settings.json
    if [ -f "$HOME/.claude/settings.json" ]; then
        echo -e "  ✅ ~/.claude/settings.json: ${YELLOW}已存在${NC}"
        local settings_size=$(stat -c%s "$HOME/.claude/settings.json" 2>/dev/null || echo "0")
        echo -e "     文件大小: ${YELLOW}${settings_size} bytes${NC}"
        echo -e "     最后修改: ${YELLOW}$(stat -c%y "$HOME/.claude/settings.json" 2>/dev/null || echo "未知")${NC}"
    else
        echo -e "  ❌ ~/.claude/settings.json: ${YELLOW}不存在${NC}"
    fi
    
    # Check ~/.claude.json
    if [ -f "$HOME/.claude.json" ]; then
        echo -e "  ✅ ~/.claude.json: ${YELLOW}已存在${NC}"
        local claude_json_size=$(stat -c%s "$HOME/.claude.json" 2>/dev/null || echo "0")
        echo -e "     文件大小: ${YELLOW}${claude_json_size} bytes${NC}"
    else
        echo -e "  ❌ ~/.claude.json: ${YELLOW}不存在${NC}"
    fi
    
    # Check ~/.claude-code-router/config.json
    if [ -f "$HOME/.claude-code-router/config.json" ]; then
        echo -e "  ✅ ~/.claude-code-router/config.json: ${YELLOW}已存在${NC}"
        local router_config_size=$(stat -c%s "$HOME/.claude-code-router/config.json" 2>/dev/null || echo "0")
        echo -e "     文件大小: ${YELLOW}${router_config_size} bytes${NC}"
    else
        echo -e "  ❌ ~/.claude-code-router/config.json: ${YELLOW}不存在${NC}"
    fi
    echo ""
    
    # Provide troubleshooting information if packages are not found
    if [[ "$claude_code_status" == "❌ 未安装" ]] && [[ "$router_status" == "❌ 未安装" ]]; then
        echo -e "${RED}故障诊断和解决方案:${NC}"
        echo -e "${YELLOW}----------------------------------------${NC}"
        echo -e "如果包显示未安装，请尝试以下解决方案："
        echo ""
        echo -e "1. ${BLUE}检查是否安装成功:${NC}"
        echo -e "   npm list -g @anthropic-ai/claude-code"
        echo -e "   npm list -g @musistudio/claude-code-router"
        echo ""
        echo -e "2. ${BLUE}验证可执行文件:${NC}"
        echo -e "   which claude  # Claude Code 可执行文件名"
        echo -e "   which ccr     # Claude Code Router 可执行文件名"
        echo ""
        echo -e "3. ${BLUE}手动重新安装:${NC}"
        echo -e "   npm install -g @anthropic-ai/claude-code"
        echo -e "   npm install -g @musistudio/claude-code-router"
        echo ""
        echo -e "4. ${BLUE}如果全局安装失败，使用本地安装:${NC}"
        echo -e "   npm install --prefix ~/.local @anthropic-ai/claude-code"
        echo -e "   npm install --prefix ~/.local @musistudio/claude-code-router"
        echo ""
        echo -e "5. ${BLUE}检查并添加到 PATH:${NC}"
        echo -e "   echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc"
        echo -e "   source ~/.bashrc"
        echo ""
        echo -e "6. ${BLUE}重新加载终端后再次检查${NC}"
        echo -e "${YELLOW}----------------------------------------${NC}"
        echo ""
        echo -e "${BLUE}检查配置文件状态:${NC}"
        echo -e "  ls -la ~/.claude/settings.json"
        echo -e "  ls -la ~/.claude.json"
        echo -e "  ls -la ~/.claude-code-router/config.json"
        echo ""
    elif [[ "$claude_code_status" == *"本地"* ]] || [[ "$router_status" == *"本地"* ]]; then
        echo -e "${YELLOW}使用提示:${NC}"
        echo -e "${YELLOW}----------------------------------------${NC}"
        echo -e "检测到本地安装，如果命令不可用，请:"
        echo -e "1. 重新加载终端: source ~/.bashrc 或 source ~/.zshrc"
        echo -e "2. 或直接使用完整路径执行命令"
        echo -e "${YELLOW}----------------------------------------${NC}"
        echo ""
    fi
    
    echo -e "${BLUE}========================================${NC}"
}

# Main execution
main() {
    # Step 1: Detect OS and Shell
    detect_os_and_shell
    echo
    
    # Step 2: Add environment variables
    add_env_vars
    echo
    
    # Step 3: Update .claude.json
    update_claude_json
    echo
    
    # Step 4: Install npm packages
    install_npm_packages
    echo
    
    # Step 5: Configure Claude Code settings
    configure_claude_code_settings
    echo
    
    # Step 6: Configure Claude Code Router
    configure_claude_code_router
    echo
    
    # Step 7: Activate configuration
    activate_config
    echo
    
    # Step 8: Verify configuration
    verify_config
    echo
    
    # Step 9: Display version and installation path information
    print_version_and_path_info
    echo
    
    print_success "Claude Code环境配置完成！"
    echo -e "${BLUE}========================================${NC}"

    # Display installed packages info
    echo -e "${BLUE}已安装的包：${NC}"
    echo -e "📦 @anthropic-ai/claude-code - Claude Code CLI 工具"
    echo -e "📦 @musistudio/claude-code-router - Claude Code 路由器"
    echo ""
    
    # Step 10: Start Claude Code Router service
    start_ccr_service
    echo
    
    # Important reminder in red
    echo
    echo -e "${RED}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║                                                          ║${NC}"
    echo -e "${RED}║    请关闭终端后重新打开，开始 claude code 使用～        ║${NC}"
    echo -e "${RED}║                                                          ║${NC}"
    echo -e "${RED}║    可以运行 'claude --help' 查看使用帮助                ║${NC}"
    echo -e "${RED}║    可以运行 'ccr --help' 查看路由器帮助                 ║${NC}"
    echo -e "${RED}║                                                          ║${NC}"
    echo -e "${RED}╚══════════════════════════════════════════════════════════╝${NC}"
    echo
}

# Run main function
main

# Exit successfully
exit 0