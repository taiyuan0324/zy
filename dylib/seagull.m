// seagull.m — 汽水音乐 21.x 自签名包补丁 (v4)
//
// ===== v1~v3 复盘（打错靶了，这次必须改路线）=====
//   v1: 包了 NSURLSession + 换 rootVC  -> 卡启动/无网（事故）
//   v2: 只吞 AntiCheatViewController present/push -> 安全弹窗消失（有效）
//   v3: 扫 ObjC 无参 BOOL getter 伪装正版判据 -> 网络出错依旧
//
// 用户实测结论（决定性）：
//   1) "安全弹窗从第一版就没弹出过"      => UI 拦截一直有效，这条链路已结束
//   2) "一直都是网络问题"                => 从头到尾唯一症状是 NoNetView
//   3) "关掉 Loon 还是网络问题"          => 与代理/DNS/QUIC/证书完全无关
//   4) 纯自签名（未注入任何 dylib）就是「安全提示 + 网络出错」
//      => 网络出错源于【签名/渠道校验失败后的本地降级】，不是我们注入的 dylib，
//         也不是反作弊弹窗带出来的副作用。
//
// 静态证据（21.7.0 strings）：
//   - queue_init_depend_on_sec_uid_v3        请求队列初始化依赖 sec_uid
//   - notAntiCheat / batch_request_config    批处理准入条件枚举（命中反作弊就关掉）
//   - hitAntiCheat, disable DeepLink
//   - _hitAntiCheat / _isSwitchOn           Swift 存储属性（ivar），不是 ObjC getter
//       => v3 只扫 method list，天然扫不到，scan 可能 = 0
//   - MSManagerML / MetaSecService / BytedCert / bd-ticket-guard / checkSignFail
//       => 判据在 C++/Swift 层做签名 blob / cdhash / team-id 比对
//   - appStoreReceiptURL (1 命中)           自签包无 StoreKit receipt
//   - isAppStoreChannel (ObjC 类方法)       渠道判据
//   - MobileSubstrate/libsubstrate/frida/_dyld_get_image_name
//       => App 会遍历 dyld image 做注入检测
//
// ===== v4 策略 =====
//  A. 不再依赖 NSLog：内置【可见诊断弹窗】+ 一键复制 + 写 Documents/seagull_diag.txt
//     （用户不用连 Xcode 控制台，截图/粘贴即可回传真相）
//  B. 从「伪装 getter」升级到「伪装渠道凭证」：
//       - NSBundle appStoreReceiptURL -> 返回确实存在的文件 URL
//       - NSFileManager fileExistsAtPath: -> 越狱/注入特征路径 NO，receipt 路径 YES
//       - NSUserDefaults 敏感 key -> NO / nil
//       - NSProcessInfo environment -> 抹掉 DYLD_* 注入变量
//  C. 保留 v3 的全量 BOOL getter 伪装，但扩大安全类名 scope（含 MSManager/BytedCert）
//     并新增 ivar 枚举，把含 _hitAntiCheat 的类名打进诊断
//  D. 保留 v2 的 UI 拦截（已验证有效）
//  E. 零网络侵入：不出现 NSURLSession / dataTask / setRootViewController
//
// 事故约束（v1 永不再犯）：
//   1. 绝不包装/改写网络请求与 completion
//   2. 绝不替换根控制器设置
//   3. 系统类 hook 一律「命中才改、未命中原 IMP 透传」，且 hook 内不递归调自己
//   4. 所有安装延后到主线程，避开 dyld constructor 阶段
//   5. 全部 hook 可计数、可在诊断弹窗里核对
//
// E. 零网络侵入：本文件不引用任何会话/任务类，也不做根控制器写入
//    （CI 会扫描产物二进制，确认危险符号为零）

#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#import <objc/runtime.h>
#import <mach-o/dyld.h>
#import <stdarg.h>
#import <unistd.h>

#pragma mark - 诊断收集（可见输出，不依赖控制台）

static NSMutableString *gDiag = nil;
static int gGetterHits   = 0;   // BOOL getter 被替换数
static int gIvarClasses  = 0;   // 含 _hitAntiCheat 等 ivar 的类数
static int gDefHits      = 0;   // NSUserDefaults 敏感 key 命中数
static int gFileHits     = 0;   // fileExistsAtPath 命中数
static int gReceiptHits  = 0;   // appStoreReceiptURL 调用数
static int gEnvHits      = 0;   // environment 调用数
static int gUIBlocked    = 0;   // 反作弊 VC 被拦次数
static int gDiagPhase    = 0;   // 4s 弹窗 / 12s 只刷新文件，不重复弹

static void SGLog(NSString *fmt, ...) {
    va_list ap; va_start(ap, fmt);
    NSString *s = [[NSString alloc] initWithFormat:fmt arguments:ap];
    va_end(ap);
    NSLog(@"[SG v4] %@", s);
    if (gDiag) {
        @synchronized (gDiag) { [gDiag appendFormat:@"%@\n", s]; }
    }
}

#pragma mark - 固定返回值

static BOOL SGReturnYES(id self, SEL _cmd) { return YES; }
static BOOL SGReturnNO (id self, SEL _cmd) { return NO;  }
static void SGNoop     (id self, SEL _cmd, id arg) { (void)arg; }

// 全局强改（所有类，不限于安全模块）：这些名字在各模块含义一致，误伤概率低
static const char *kGlobalNo[] = {
    "isJailBroken", "isJailBreak", "isJailbreak", "isJailbroken",
    "btd_isJailBroken", "isInjected", "isInjectedModel", "isTampered",
    "isReSigned", "isModified", "checkSignFail", "isHitAntiCheat",
    "hitAntiCheat", "isSignCheckFailed", "isNonAppStore", NULL
};
static const char *kGlobalYes[] = {
    "isAppStoreChannel", "isAppStoreBuild", "isFromAppStore",
    "isOfficialChannel", "isAppStoreReceiptValid", NULL
};
// 只在安全/风控类名范围内替换：isSwitchOn 在 IM/青少年模式里是正常 UI 开关，别全局改
static const char *kScopedNo[] = {
    "isSwitchOn", "shouldShowAntiCheat", "isAntiCheatOn", "antiCheatEnabled",
    "shouldBlockRequest", "isRiskDevice", "isRequestBlocked", NULL
};
static const char *kNoopSels[] = {
    "checkSignAuthIfNeed:", "reportAntiCheatIfNeed", "startAntiCheatMonitor",
    "detectInjectedLibraries", NULL
};

static BOOL SGInList(const char *s, const char **list) {
    for (int i = 0; list[i]; i++) if (strcmp(s, list[i]) == 0) return YES;
    return NO;
}

static BOOL SGSafeBoolGetter(Method m) {
    if (method_getNumberOfArguments(m) != 2) return NO;
    char ret[16] = {0};
    method_getReturnType(m, ret, sizeof(ret));
    return ret[0] == 'B' || ret[0] == 'c' || ret[0] == 'b';
}

// 扩大后的安全/风控类名范围（Swift mangled 名里也含这些子串）
static BOOL SGSecScope(NSString *name) {
    static NSString *keys[] = {
        @"STSecurity", @"AntiCheat", @"MetaSec", @"MSManager", @"Security",
        @"BytedCert", @"TicketGuard", @"BatchRequest", @"STCoreStart", @"SignCheck"
    };
    for (int i = 0; i < (int)(sizeof(keys)/sizeof(keys[0])); i++) {
        if ([name rangeOfString:keys[i]].location != NSNotFound) return YES;
    }
    return NO;
}

#pragma mark - ObjC 全量扫描（替换 getter + 枚举 ivar）

static void SGPatchList(Class c, NSString *name, BOOL secScope, BOOL isMeta) {
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
        SGLog(@"GETTER %@[%@ %s] enc=%s", isMeta ? @"+" : @"-", name, sn, te);

        if (wantNoop) {
            char ret[16] = {0};
            method_getReturnType(m, ret, sizeof(ret));
            if (ret[0] != 'v') { SGLog(@"  skip noop (ret=%s)", ret); continue; }
            method_setImplementation(m, (IMP)SGNoop);
            gGetterHits++;
            continue;
        }
        if (!SGSafeBoolGetter(m)) { SGLog(@"  skip (not no-arg BOOL getter)"); continue; }
        method_setImplementation(m, wantYes ? (IMP)SGReturnYES : (IMP)SGReturnNO);
        SGLog(@"  -> forced %@", wantYes ? @"YES" : @"NO");
        gGetterHits++;
    }
    free(ms);
}

static void SGDumpIvars(Class c, NSString *name) {
    unsigned ic = 0;
    Ivar *ivs = class_copyIvarList(c, &ic);
    if (!ivs) return;
    for (unsigned j = 0; j < ic; j++) {
        const char *iname = ivar_getName(ivs[j]);
        if (!iname) continue;
        if (strstr(iname, "hitAntiCheat") || strstr(iname, "checkSignFail") ||
            strstr(iname, "isSwitchOn")   || strstr(iname, "isInjected")) {
            if (gIvarClasses < 25) SGLog(@"IVAR [%@] %s type=%s", name, iname, ivar_getTypeEncoding(ivs[j]) ?: "?");
            gIvarClasses++;
        }
    }
    free(ivs);
}

static void SGScan(void) {
    int n = objc_getClassList(NULL, 0);
    if (n <= 0) { SGLog(@"objc_getClassList returned 0"); return; }
    Class *all = (Class *)malloc(sizeof(Class) * (size_t)n);
    n = objc_getClassList(all, n);
    for (int i = 0; i < n; i++) {
        Class c = all[i];
        const char *cn = class_getName(c);
        NSString *name = cn ? [NSString stringWithUTF8String:cn] : @"?";
        BOOL scope = SGSecScope(name);
        SGPatchList(c, name, scope, NO);
        SGPatchList(object_getClass((id)c), name, scope, YES);
        if (scope) SGDumpIvars(c, name);
    }
    free(all);
    SGLog(@"scan finished: %d method(s) patched, %d ivar(s) found", gGetterHits, gIvarClasses);
}

#pragma mark - B. 渠道凭证伪装

typedef BOOL (*BoolForStrFn)(id, SEL, NSString *);
typedef id   (*ObjForStrFn) (id, SEL, NSString *);
typedef BOOL (*FileExistsFn)(id, SEL, NSString *);
typedef NSURL *(*ReceiptFn) (id, SEL);
typedef NSDictionary *(*EnvFn)(id, SEL);

static BoolForStrFn o_boolForKey;
static ObjForStrFn  o_objectForKey;
static FileExistsFn o_fileExists;
static ReceiptFn    o_receipt;
static EnvFn        o_environment;

// 注意：NSUserDefaults 的 boolForKey/objectForKey 是超高频系统方法，
// 这里【必须精确匹配】，绝不用 "risk"/"sign"/"break" 这类短词子串，
// 否则会误伤大量正常业务配置（v1 事故就是侵入太广）。
static BOOL SGSensitiveKey(NSString *k) {
    if (!k) return NO;
    static NSSet *exact = nil;
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        exact = [NSSet setWithObjects:
            @"isJailBroken", @"jailbroken", @"isInjected", @"injected",
            @"hitAntiCheat", @"isHitAntiCheat", @"checkSignFail",
            @"isReSigned", @"isTampered", @"isNonAppStore",
            @"antiCheatSwitchOn", @"isSignCheckFailed", nil];
    });
    return [exact containsObject:k];
}

static BOOL sg_boolForKey(id self, SEL _cmd, NSString *key) {
    if (SGSensitiveKey(key)) { gDefHits++; return NO; }
    return o_boolForKey ? o_boolForKey(self, _cmd, key) : NO;
}
static id sg_objectForKey(id self, SEL _cmd, NSString *key) {
    if (SGSensitiveKey(key)) { gDefHits++; return nil; }
    return o_objectForKey ? o_objectForKey(self, _cmd, key) : nil;
}

static BOOL SGJailPath(NSString *p) {
    if (!p) return NO;
    NSString *l = [p lowercaseString];
    NSArray *bad = @[@"/applications/cydia.app", @"/library/mobilesubstrate",
                     @"/usr/libexec/cydia", @"/var/lib/apt", @"/bin/bash",
                     @"/usr/sbin/sshd", @"mobilesubstrate.dylib",
                     @"frida", @"cycript", @"libsubstrate"];
    for (NSString *b in bad) if ([l rangeOfString:b].location != NSNotFound) return YES;
    return NO;
}
static BOOL sg_fileExists(id self, SEL _cmd, NSString *path) {
    // 只针对【精确的自签名铁证路径】动手，其余一律原 IMP 透传，
    // 避免把 App 正常的资源/缓存存在性判断搞乱（v1 事故防线）。
    if (path) {
        NSString *last = [path lastPathComponent];
        if ([last isEqualToString:@"embedded.mobileprovision"] ||
            [last isEqualToString:@"_CodeSignature"] ||
            [last isEqualToString:@"SC_Info"]) { gFileHits++; return NO; }
        if ([last isEqualToString:@"receipt"] || [last isEqualToString:@"sandboxReceipt"]) {
            gFileHits++; return YES;
        }
    }
    if (SGJailPath(path)) { gFileHits++; return NO; }
    return o_fileExists ? o_fileExists(self, _cmd, path) : NO;
}

// 自签包没有 StoreKit receipt。很多渠道判据只做「URL 非空 + 文件存在」，
// 这里返回 bundle 里确实存在的文件，让 existence check 通过。
static NSURL *sg_receipt(id self, SEL _cmd) {
    gReceiptHits++;
    NSURL *b = [[NSBundle mainBundle] bundleURL];
    NSURL *f = [b URLByAppendingPathComponent:@"Info.plist"];
    if (f) return f;
    return o_receipt ? o_receipt(self, _cmd) : nil;
}

static NSDictionary *sg_environment(id self, SEL _cmd) {
    NSDictionary *e = o_environment ? o_environment(self, _cmd) : nil;
    NSMutableDictionary *m = [e mutableCopy];
    if (!m) return e;
    BOOL changed = NO;
    for (NSString *k in [e allKeys]) {
        if ([k hasPrefix:@"DYLD_"] || [k rangeOfString:@"INSERT_LIBRARIES"].location != NSNotFound) {
            [m removeObjectForKey:k]; changed = YES; gEnvHits++;
        }
    }
    return changed ? m : e;
}

#pragma mark - D. UI 兜底（v2，已验证有效）

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
        gUIBlocked++;
        SGLog(@"blocked present %@", NSStringFromClass([vc class]));
        if (done) done();       // 必调 completion，否则调用方状态机卡死
        return;
    }
    if (o_present) o_present(self, _cmd, vc, anim, (id)done);
}
static void sg_push(id self, SEL _cmd, UIViewController *vc, BOOL anim) {
    if (SGIsAntiCheat(vc)) { gUIBlocked++; SGLog(@"blocked push %@", NSStringFromClass([vc class])); return; }
    if (o_push) o_push(self, _cmd, vc, anim);
}
static void sg_makeKey(id self, SEL _cmd) {
    id root = nil;
    @try { root = [self valueForKey:@"rootViewController"]; } @catch (NSException *e) {}
    if (SGIsAntiCheat(root)) {
        gUIBlocked++;
        SGLog(@"blocked makeKeyAndVisible for %@", NSStringFromClass([root class]));
        @try { [self setHidden:YES]; } @catch (NSException *e) {}
        return;
    }
    if (o_makeKey) o_makeKey(self, _cmd);
}

static void SGInstall(Class cls, SEL sel, IMP imp, IMP *slot) {
    if (!cls || !sel) return;
    Method m = class_getInstanceMethod(cls, sel);
    if (!m) { SGLog(@"install MISS %@ %@", NSStringFromClass(cls), NSStringFromSelector(sel)); return; }
    // 必须在替换【之前】保存原 IMP：class_replaceMethod 之后 m 指向的实现已是新的，
    // 那时再 method_getImplementation(m) 会让 o_present 指向自己 -> 死递归（v1 事故同类）
    IMP old = method_getImplementation(m);
    class_replaceMethod(cls, sel, imp, method_getTypeEncoding(m));
    *slot = old;
}

#pragma mark - A. 可见诊断弹窗

static UIViewController *SGRootVC(void) {
    UIViewController *root = nil;
    if (@available(iOS 13.0, *)) {
        for (UIScene *scene in [UIApplication sharedApplication].connectedScenes) {
            if (![scene isKindOfClass:[UIWindowScene class]]) continue;
            for (UIWindow *w in ((UIWindowScene *)scene).windows) {
                if (w.isKeyWindow && w.rootViewController) { root = w.rootViewController; break; }
            }
            if (root) break;
        }
    }
    if (!root) {
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
        root = [UIApplication sharedApplication].keyWindow.rootViewController;
#pragma clang diagnostic pop
    }
    int guard = 0;
    while (root.presentedViewController && guard++ < 6) root = root.presentedViewController;
    return root;
}

static void SGShowDiag(void) {
    // 把最终快照补进诊断文本
    SGLog(@"--- runtime totals ---");
    SGLog(@"getters=%d ivars=%d defaults=%d fileExists=%d receipt=%d env=%d uiBlocked=%d",
          gGetterHits, gIvarClasses, gDefHits, gFileHits, gReceiptHits, gEnvHits, gUIBlocked);
    SGLog(@"dyld images=%u", _dyld_image_count());
    for (uint32_t i = 0; i < _dyld_image_count(); i++) {
        const char *p = _dyld_get_image_name(i);
        if (!p) continue;
        NSString *s = [NSString stringWithUTF8String:p];
        if ([s rangeOfString:@"seagull"].location != NSNotFound ||
            [s rangeOfString:@"libluna"].location != NSNotFound ||
            [s rangeOfString:@"SchubertAppStore.app/"].location != NSNotFound) {
            SGLog(@"IMAGE[%u] %@", i, s);
        }
    }
    // 用 POSIX access() 绕开自己装的 fileExistsAtPath: hook，拿真实磁盘状态
    NSString *bp = [[NSBundle mainBundle] bundlePath];
    NSString *mp = [bp stringByAppendingPathComponent:@"embedded.mobileprovision"];
    NSString *cs = [bp stringByAppendingPathComponent:@"_CodeSignature"];
    NSString *sc = [bp stringByAppendingPathComponent:@"SC_Info"];
    SGLog(@"REAL embedded.mobileprovision = %@", access([mp fileSystemRepresentation], F_OK) == 0 ? @"YES" : @"NO");
    SGLog(@"REAL _CodeSignature = %@", access([cs fileSystemRepresentation], F_OK) == 0 ? @"YES" : @"NO");
    SGLog(@"REAL SC_Info = %@", access([sc fileSystemRepresentation], F_OK) == 0 ? @"YES" : @"NO");
    NSURL *r = [[NSBundle mainBundle] appStoreReceiptURL];
    SGLog(@"receipt URL(已伪装) = %@", r ?: (id)@"(nil)");
    SGLog(@"bundle id = %@", [[NSBundle mainBundle] bundleIdentifier]);
    // 把注入的 dylib 名字也列出来，用于判断 dyld image 检测是否会被触发
    for (uint32_t i = 0; i < _dyld_image_count(); i++) {
        const char *p = _dyld_get_image_name(i);
        if (!p) continue;
        NSString *s = [NSString stringWithUTF8String:p];
        if ([s rangeOfString:@"SchubertAppStore.app/"].location != NSNotFound &&
            [s rangeOfString:@".dylib"].location != NSNotFound) {
            SGLog(@"INJECTED image[%u] %@", i, [s lastPathComponent]);
        }
    }

    // 只读 dump：App 自己写进 NSUserDefaults 的错误/网络状态（不改任何值）
    @try {
        NSDictionary *rep = [[NSUserDefaults standardUserDefaults] dictionaryRepresentation];
        int shown = 0;
        NSArray *want = @[@"error", @"fail", @"network", @"neterror", @"sign",
                          @"cheat", @"jail", @"inject", @"secuid", @"device"];
        for (NSString *k in [[rep allKeys] sortedArrayUsingSelector:@selector(compare:)]) {
            NSString *l = [k lowercaseString];
            BOOL hit = NO;
            for (NSString *w in want) if ([l rangeOfString:w].location != NSNotFound) { hit = YES; break; }
            if (!hit || shown >= 40) continue;
            id v = rep[k];
            SGLog(@"UD %@ = %@", k, [v isKindOfClass:[NSData class]] ? @"<data>" : v);
            shown++;
        }
        SGLog(@"UD matched keys = %d / total %lu", shown, (unsigned long)rep.count);
    } @catch (NSException *e) { SGLog(@"UD dump failed: %@", e.reason); }

    // 写文件（若开了文件共享，可用「文件」App / 爱思助手导出）
    @try {
        NSString *doc = NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
        if (doc) {
            NSString *fp = [doc stringByAppendingPathComponent:@"seagull_diag.txt"];
            [[gDiag copy] writeToFile:fp atomically:YES encoding:NSUTF8StringEncoding error:nil];
            SGLog(@"diag written: %@", fp);
        }
    } @catch (NSException *e) { SGLog(@"diag write failed: %@", e.reason); }

    if (gDiagPhase++ > 0) { SGLog(@"(12s refresh — alert suppressed, file updated)"); return; }

    UIViewController *root = SGRootVC();
    if (!root) { SGLog(@"NO ROOT VC — 诊断只能看控制台/文件"); return; }

    NSString *title = @"[SG v4] 自签名诊断";
    NSString *msg = [NSString stringWithFormat:
        @"getter 命中 %d / ivar 类 %d\n"
        @"defaults %d / file %d / receipt %d / env %d\n"
        @"反作弊 UI 拦截 %d\n"
        @"dyld images %u\n\n"
        @"完整清单见控制台或 Documents/seagull_diag.txt\n"
        @"点「复制诊断」把全文粘贴给海鸥",
        gGetterHits, gIvarClasses, gDefHits, gFileHits, gReceiptHits, gEnvHits,
        gUIBlocked, _dyld_image_count()];

    UIAlertController *a = [UIAlertController alertControllerWithTitle:title
                                                              message:msg
                                                       preferredStyle:UIAlertControllerStyleAlert];
    [a addAction:[UIAlertAction actionWithTitle:@"复制诊断"
                                          style:UIAlertActionStyleDefault
                                        handler:^(UIAlertAction *x) {
        [UIPasteboard generalPasteboard].string = [gDiag copy] ?: @"";
    }]];
    [a addAction:[UIAlertAction actionWithTitle:@"关闭" style:UIAlertActionStyleCancel handler:nil]];
    @try { [root presentViewController:a animated:YES completion:nil]; }
    @catch (NSException *e) { SGLog(@"diag alert failed: %@", e.reason); }
}

#pragma mark - 安装

__attribute__((constructor))
static void SGEntry(void) {
    gDiag = [NSMutableString new];
    SGLog(@"seagull v4 loaded (%s) — 渠道凭证伪装 + 可见诊断，零网络侵入", __DATE__);

    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.3 * NSEC_PER_SEC)),
                   dispatch_get_main_queue(), ^{
        // B. 渠道凭证（先装，越早越好）
        SGInstall(objc_getClass("NSBundle"), @selector(appStoreReceiptURL), (IMP)sg_receipt, (IMP *)&o_receipt);
        SGInstall(objc_getClass("NSFileManager"), @selector(fileExistsAtPath:), (IMP)sg_fileExists, (IMP *)&o_fileExists);
        SGInstall(objc_getClass("NSUserDefaults"), @selector(boolForKey:), (IMP)sg_boolForKey, (IMP *)&o_boolForKey);
        SGInstall(objc_getClass("NSUserDefaults"), @selector(objectForKey:), (IMP)sg_objectForKey, (IMP *)&o_objectForKey);
        SGInstall(objc_getClass("NSProcessInfo"), @selector(environment), (IMP)sg_environment, (IMP *)&o_environment);

        // D. UI 拦截
        SGInstall(objc_getClass("UIViewController"),
                  @selector(presentViewController:animated:completion:), (IMP)sg_present, (IMP *)&o_present);
        SGInstall(objc_getClass("UINavigationController"),
                  @selector(pushViewController:animated:), (IMP)sg_push, (IMP *)&o_push);
        SGInstall(objc_getClass("UIWindow"), @selector(makeKeyAndVisible), (IMP)sg_makeKey, (IMP *)&o_makeKey);

        // C. 全量 ObjC 扫描
        SGScan();
        SGLog(@"install done");
    });

    // A. 4 秒后弹可见诊断（等首页/错误页起来、等反作弊判定跑完）
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(4.0 * NSEC_PER_SEC)),
                   dispatch_get_main_queue(), ^{ SGShowDiag(); });
    // 12 秒二次刷新：把启动后较晚才写入的网络错误也捞进文件，不重复弹窗
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(12.0 * NSEC_PER_SEC)),
                   dispatch_get_main_queue(), ^{ SGShowDiag(); });
}
