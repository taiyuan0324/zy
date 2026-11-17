// seagull.m — 汽水音乐 21.x 自签名包补丁 (v3)
//
// v3 目标：让本地反作弊判定认为「正版 App Store 安装 / 未越狱 / 未注入 / 云控开关关闭」
//          从而同时消除「当前版本不安全」弹窗 与 随之而来的「网络出错」。
//
// 依据（21.7.0 静态）：
//   - isAppStoreChannel                    渠道判据（BDA 工具类类方法）
//   - isJailBroken / isJailBreak / isJailbreak / btd_isJailBroken
//     isInjected / _isInjected / _isJailbreak / checkSignFail
//     checkSignatureUrl / checkSignAuthIfNeed:        本地越狱/注入/签名检测
//   - STSecurity.AntiCheatViewController + 当前版本不安全 + 请在正规应用市场下载
//     + isSwitchOn + RSA 验签公钥                     云控反作弊开关
//   - hitAntiCheat, disable DeepLink / notAntiCheat（准入条件枚举）
//     + batch_request_config                          命中后本地降级批量请求
//   - _hitAntiCheat / msManager(MSManagerML) / MetaSecService   风控状态机
//
// 事故约束（v1 翻车复盘）：
//   1. 绝不包装网络请求；本文件不出现任何网络会话符号
//   2. 绝不替换根控制器设置；只拦「独立 window 把反作弊 VC 顶到前台」这一条
//   3. 只替换「无参数 + 返回 BOOL」的 getter，带参数方法只做 void no-op
//   4. present 被拦必调 completion
//   5. 全部安装延后到主线程，避开 dyld constructor 阶段
//
// 运行时自诊断：每个命中都会 NSLog 出 类名 / +/- / selector / typeEncoding，
// 装完看控制台即可知道哪些 hook 真的生效，便于下一轮精准补点。

#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#import <objc/runtime.h>

#pragma mark - 固定返回值

static BOOL SGReturnYES(id self, SEL _cmd) { return YES; }
static BOOL SGReturnNO (id self, SEL _cmd) { return NO;  }
static void SGNoop     (id self, SEL _cmd, id arg) { (void)arg; }

static const char *kGlobalNo[] = {
    "isJailBroken", "isJailBreak", "isJailbreak", "isJailbroken",
    "btd_isJailBroken", "isInjected", "isInjectedModel",
    "checkSignFail", "hitAntiCheat", "isHitAntiCheat",
    "isTampered", "isReSigned", "isModified", NULL
};
static const char *kGlobalYes[] = {
    "isAppStoreChannel", "isAppStoreBuild", "isFromAppStore",
    "isOfficialChannel", NULL
};
// 仅在安全模块类名范围内替换，避免误伤 IM / 青少年模式 / 隐私设置里同名开关
static const char *kScopedNo[] = {
    "isSwitchOn", "shouldShowAntiCheat", "isAntiCheatOn",
    "antiCheatEnabled", "shouldBlockRequest", "isRiskDevice", NULL
};
static const char *kNoopSels[] = {
    "checkSignAuthIfNeed:", "reportAntiCheatIfNeed", NULL
};

static BOOL SGInList(const char *s, const char **list) {
    for (int i = 0; list[i]; i++) if (strcmp(s, list[i]) == 0) return YES;
    return NO;
}

// 只有「恰好 self+_cmd 两个参数 且 返回 BOOL/bool/char」的 getter 才安全替换
static BOOL SGSafeBoolGetter(Method m) {
    if (method_getNumberOfArguments(m) != 2) return NO;
    char ret[16] = {0};
    method_getReturnType(m, ret, sizeof(ret));
    return ret[0] == 'B' || ret[0] == 'c' || ret[0] == 'b';
}

#pragma mark - 扫描并替换

static void SGPatchList(Class c, NSString *name, BOOL secScope, BOOL isMeta, int *hits) {
    unsigned mc = 0;
    Method *ms = class_copyMethodList(c, &mc);
    if (!ms) return;
    for (unsigned j = 0; j < mc; j++) {
        Method m = ms[j];
        const char *sn = sel_getName(method_getName(m));

        BOOL wantNo   = SGInList(sn, kGlobalNo);
        BOOL wantYes  = SGInList(sn, kGlobalYes);
        BOOL wantNoop = SGInList(sn, kNoopSels);
        if (secScope) wantNo = wantNo || SGInList(sn, kScopedNo);
        if (!wantNo && !wantYes && !wantNoop) continue;

        const char *te = method_getTypeEncoding(m) ?: "?";
        NSLog(@"[SG v3] HIT %@[%@ %s] enc=%s", isMeta ? @"+" : @"-", name, sn, te);

        if (wantNoop) {
            char ret[16] = {0};
            method_getReturnType(m, ret, sizeof(ret));
            if (ret[0] != 'v') {
                NSLog(@"[SG v3]   skip noop (non-void return)");
                continue;
            }
            method_setImplementation(m, (IMP)SGNoop);
            (*hits)++;
            continue;
        }
        if (!SGSafeBoolGetter(m)) {
            NSLog(@"[SG v3]   skip (not a no-arg BOOL getter)");
            continue;
        }
        method_setImplementation(m, wantYes ? (IMP)SGReturnYES : (IMP)SGReturnNO);
        NSLog(@"[SG v3]   -> forced %@", wantYes ? @"YES" : @"NO");
        (*hits)++;
    }
    free(ms);
}

static void SGScan(void) {
    int n = objc_getClassList(NULL, 0);
    if (n <= 0) return;
    Class *all = (Class *)malloc(sizeof(Class) * (size_t)n);
    n = objc_getClassList(all, n);
    int hits = 0;
    for (int i = 0; i < n; i++) {
        Class c = all[i];
        const char *cn = class_getName(c);
        NSString *name = cn ? [NSString stringWithUTF8String:cn] : @"?";
        BOOL secScope = ([name rangeOfString:@"STSecurity"].location != NSNotFound ||
                         [name rangeOfString:@"AntiCheat"].location != NSNotFound ||
                         [name rangeOfString:@"MetaSec"].location   != NSNotFound ||
                         [name rangeOfString:@"MSManager"].location != NSNotFound);
        SGPatchList(c, name, secScope, NO, &hits);                    // 实例方法
        SGPatchList(object_getClass(c), name, secScope, YES, &hits);  // 类方法（元类）
    }
    free(all);
    NSLog(@"[SG v3] scan finished: %d method(s) patched", hits);
}

#pragma mark - UI 兜底（保留 v2，并补独立 window）

static BOOL SGIsAntiCheat(id vc) {
    if (!vc) return NO;
    NSString *n = NSStringFromClass([vc class]);
    return n && [n rangeOfString:@"AntiCheatViewController"].location != NSNotFound;
}

typedef void (*PresentFn)(id, SEL, id, BOOL, id);
typedef void (*PushFn)(id, SEL, id, BOOL);
typedef void (*VoidFn)(id, SEL);

static PresentFn o_present;
static PushFn    o_push;
static VoidFn    o_makeKey;

static void sg_present(id self, SEL _cmd, UIViewController *vc, BOOL anim, void (^done)(void)) {
    if (SGIsAntiCheat(vc)) {
        NSLog(@"[SG v3] blocked present %@", NSStringFromClass([vc class]));
        if (done) done();
        return;
    }
    if (o_present) o_present(self, _cmd, vc, anim, (id)done);
}
static void sg_push(id self, SEL _cmd, UIViewController *vc, BOOL anim) {
    if (SGIsAntiCheat(vc)) {
        NSLog(@"[SG v3] blocked push %@", NSStringFromClass([vc class]));
        return;
    }
    if (o_push) o_push(self, _cmd, vc, anim);
}
// 反作弊 VC 可能挂在独立高电平 UIWindow 上（stSecurityRegister 附近有 setWindowLevel:）
// 只在这个 window 的 rootVC 明确是反作弊 VC 时阻止它成为 key window，正常 window 全放行。
static void sg_makeKey(id self, SEL _cmd) {
    id root = nil;
    @try { root = [self valueForKey:@"rootViewController"]; } @catch (NSException *e) {}
    if (SGIsAntiCheat(root)) {
        NSLog(@"[SG v3] blocked makeKeyAndVisible for %@", NSStringFromClass([root class]));
        @try { [self setHidden:YES]; } @catch (NSException *e) {}
        return;
    }
    if (o_makeKey) o_makeKey(self, _cmd);
}

static void SGInstall(Class cls, SEL sel, IMP imp, IMP *slot) {
    if (!cls || !sel) return;
    Method m = class_getInstanceMethod(cls, sel);
    if (!m) return;
    IMP old = class_replaceMethod(cls, sel, imp, method_getTypeEncoding(m));
    *slot = old ? old : method_getImplementation(m);
}

#pragma mark - 安装

__attribute__((constructor))
static void SGEntry(void) {
    NSLog(@"[SG v3] seagull loaded (%s) — verdict spoof, zero network intrusion", __DATE__);
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.3 * NSEC_PER_SEC)),
                   dispatch_get_main_queue(), ^{
        SGInstall(objc_getClass("UIViewController"),
                  @selector(presentViewController:animated:completion:),
                  (IMP)sg_present, (IMP *)&o_present);
        SGInstall(objc_getClass("UINavigationController"),
                  @selector(pushViewController:animated:),
                  (IMP)sg_push, (IMP *)&o_push);
        SGInstall(objc_getClass("UIWindow"),
                  @selector(makeKeyAndVisible),
                  (IMP)sg_makeKey, (IMP *)&o_makeKey);
        SGScan();
        NSLog(@"[SG v3] install done");
    });
}
