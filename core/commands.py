"""命令清单：按 op 等级分组，附中文说明和最低版本要求。"""

# 格式：(命令名, 中文说明, 最低版本元组)
# min_version 为 None 表示从 1.16.5 起就存在
PLAYER_COMMANDS = {
    2: [
        ("clear",         "清空物品栏",         None),
        ("clone",         "复制方块区域",       None),
        ("damage",        "造成伤害",           (1, 19, 4)),
        ("data",          "操作NBT数据",        None),
        ("difficulty",    "设置难度",           None),
        ("effect",        "给予药水效果",       None),
        ("enchant",       "附魔",               None),
        ("execute",       "执行命令",           None),
        ("fill",          "填充方块",           None),
        ("fillbiome",     "填充生物群系",       (1, 19, 3)),
        ("forceload",     "强制加载区块",       None),
        ("function",      "运行函数",           None),
        ("gamemode",      "切换游戏模式",       None),
        ("gamerule",      "设置游戏规则",       None),
        ("give",          "给予物品",           None),
        ("item",          "操作物品",           (1, 17, 0)),
        ("jfr",           "Java飞行记录器",     (1, 18, 0)),
        ("kill",          "击杀实体",           None),
        ("locate",        "定位结构",           None),
        ("loot",          "生成战利品",         None),
        ("particle",      "生成粒子",           None),
        ("place",         "放置结构",           (1, 19, 0)),
        ("playsound",     "播放音效",           None),
        ("setblock",      "放置方块",           None),
        ("spawnpoint",    "设置出生点",         None),
        ("spreadplayers", "随机传送",           None),
        ("stopsound",     "停止音效",           None),
        ("summon",        "生成实体",           None),
        ("tag",           "标签管理",           None),
        ("team",          "队伍管理",           None),
        ("teleport",      "传送实体",           None),
        ("tellraw",       "发送JSON消息",       None),
        ("time",          "设置时间",           None),
        ("title",         "显示标题",           None),
        ("tp",            "传送",               None),
        ("weather",       "设置天气",           None),
        ("worldborder",   "世界边界",           None),
        ("xp",            "给予经验",           None),
    ],
    3: [
        ("ban",           "封禁玩家",           None),
        ("ban-ip",        "封禁IP",             None),
        ("banlist",       "查看封禁列表",       None),
        ("deop",          "取消OP",             None),
        ("kick",          "踢出玩家",           None),
        ("list",          "查看在线玩家",       None),
        ("op",            "给予OP",             None),
        ("pardon",        "解除封禁",           None),
        ("pardon-ip",     "解除IP封禁",         None),
        ("tick",          "控制游戏刻",         (1, 20, 3)),
        ("whitelist",     "白名单管理",         None),
    ],
    4: [
        ("stop",          "停止服务器",         None),
        ("save-all",      "保存世界",           None),
        ("save-off",      "停止自动保存",       None),
        ("save-on",       "开启自动保存",       None),
        ("reload",        "重载服务端",         None),
    ],
}


def _version_ge(version, minimum):
    """判断 version 是否 >= minimum。minimum 为 None 时返回 True。"""
    if minimum is None:
        return True
    v = tuple(version) + (0,) * (3 - len(version))
    m = tuple(minimum) + (0,) * (3 - len(minimum))
    return v >= m


def get_commands_for_version(server_version):
    """返回指定服务端版本下可用的命令字典 {op_level: [(cmd, desc), ...]}。"""
    result = {}
    for op_level, cmds in PLAYER_COMMANDS.items():
        valid = []
        for name, desc, min_ver in cmds:
            if _version_ge(server_version, min_ver):
                valid.append((name, desc))
        if valid:
            result[op_level] = valid
    return result


def all_known_commands(server_version=None):
    """所有需要审计的命令名。不传版本返回全部。"""
    cmds = set()
    for lst in PLAYER_COMMANDS.values():
        for name, _, min_ver in lst:
            if server_version is None or _version_ge(server_version, min_ver):
                cmds.add(name)
    return cmds


def commands_by_op_level(op_level, server_version=None):
    """返回 op-level 允许的所有命令名（含低级别）。"""
    result = []
    for lv in sorted(PLAYER_COMMANDS):
        if lv <= op_level:
            for name, _, min_ver in PLAYER_COMMANDS[lv]:
                if server_version is None or _version_ge(server_version, min_ver):
                    result.append(name)
    return result


def describe(cmd_name):
    """返回命令的中文说明。"""
    for lst in PLAYER_COMMANDS.values():
        for name, desc, _ in lst:
            if name == cmd_name:
                return desc
    return ""