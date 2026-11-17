// seagull.m — 汽水音乐 21.x 自签名包补丁
// 目标 1：拦掉 STSecurity.AntiCheatViewController（"当前版本不安全"弹窗）
// 目标 2：把系统网络栈响应里的 "launch_duration":30 原地改成 : 1
//
// 注意：目标 2 只对走 NSURLSession 的请求有效（beta-luna.douyin.com 那条老通道）。
//       api3-*.qishui.com 走 Cronet C++ 层，这里抓不到，需要另有关闭 Cronet 的开关。

#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#import <objc/runtime.h>

#pragma mark - 判定

static BOOL SGIsAntiCheat(id vc) {
    if (!vc) return NO;
    NSString *n = NSStringFromClass([vc class]);
    if (!n) return NO;
    return [n rangeOfString:@"AntiCheat"].location != NSNotFound
        || [n rangeOfString:@"STSecurity"].location != NSNotFound;
}

#pragma mark - 原函数指针

typedef void (*PresentFn)(id, SEL, id, BOOL, id);
typedef void (*PushFn)(id, SEL, id, BOOL);
typedef void (*RootFn)(id, SEL, id);
typedef id   (*TaskFn)(id, SEL, id, id);

static PresentFn o_present;
static PushFn    o_push;
static RootFn    o_root;
static TaskFn    o_task;

#pragma mark - JSON 原地改写

// 原串 "launch_duration":30,  与替换串 "launch_duration": 1,  都是 21 字节，
// 等长替换，不破坏 JSON 结构，也不需要重新序列化。
static NSData *SGRewrite(NSData *d) {
    if (d.length == 0) return d;
    NSData *from = [@"\"launch_duration\":30," dataUsingEncoding:NSUTF8StringEncoding];
    NSData *to   = [@"\"launch_duration\": 1," dataUsingEncoding:NSUTF8StringEncoding];
    if (from.length != to.length) return d;

    NSRange first = [d rangeOfData:from options:0 range:NSMakeRange(0, d.length)];
    if (first.location == NSNotFound) return d;

    NSMutableData *m = [d mutableCopy];
    NSInteger hit = 0;
    NSRange r = first;
    while (r.location != NSNotFound) {
        [m replaceBytesInRange:r withBytes:to.bytes length:to.length];
        hit++;
        NSUInteger tail = r.location + to.length;
        if (tail >= m.length) break;
        r = [m rangeOfData:from options:0 range:NSMakeRange(tail, m.length - tail)];
    }
    if (hit > 0) NSLog(@"[SG] launch_duration 30->1 x%ld", (long)hit);
    return m;
}

#pragma mark - Hook 实现

static void sg_present(id self, SEL _cmd, UIViewController *vc, BOOL anim, void (^done)(void)) {
    if (SGIsAntiCheat(vc)) {
        NSLog(@"[SG] blocked present %@", NSStringFromClass([vc class]));
        return;
    }
    if (o_present) o_present(self, _cmd, vc, anim, (id)done);
}

static void sg_push(id self, SEL _cmd, UIViewController *vc, BOOL anim) {
    if (SGIsAntiCheat(vc)) {
        NSLog(@"[SG] blocked push %@", NSStringFromClass([vc class]));
        return;
    }
    if (o_push) o_push(self, _cmd, vc, anim);
}

static void sg_root(id self, SEL _cmd, UIViewController *vc) {
    if (SGIsAntiCheat(vc)) {
        NSLog(@"[SG] blocked root %@", NSStringFromClass([vc class]));
        return;
    }
    if (o_root) o_root(self, _cmd, vc);
}

static id sg_task(id self, SEL _cmd, NSURLRequest *req, void (^handler)(NSData *, NSURLResponse *, NSError *)) {
    if (!o_task) return nil;
    if (!handler) return o_task(self, _cmd, req, nil);

    void (^wrapped)(NSData *, NSURLResponse *, NSError *) =
    ^(NSData *d, NSURLResponse *r, NSError *e) {
        handler(SGRewrite(d), r, e);
    };
    return o_task(self, _cmd, req, (id)wrapped);
}

#pragma mark - 安装

static void SGInstall(Class cls, SEL sel, IMP imp, IMP *slot) {
    if (!cls || !sel) return;
    Method m = class_getInstanceMethod(cls, sel);
    if (!m) { NSLog(@"[SG] method not found: %@", NSStringFromSelector(sel)); return; }
    *slot = method_getImplementation(m);
    method_setImplementation(m, imp);
    NSLog(@"[SG] hooked %@.%@", NSStringFromClass(cls), NSStringFromSelector(sel));
}

__attribute__((constructor))
static void SGEntry(void) {
    NSLog(@"[SG] seagull loaded (%s)", __DATE__);

    SGInstall(objc_getClass("UIViewController"),
              @selector(presentViewController:animated:completion:),
              (IMP)sg_present, (IMP *)&o_present);

    SGInstall(objc_getClass("UINavigationController"),
              @selector(pushViewController:animated:),
              (IMP)sg_push, (IMP *)&o_push);

    SGInstall(objc_getClass("UIWindow"),
              @selector(setRootViewController:),
              (IMP)sg_root, (IMP *)&o_root);

    SGInstall(objc_getClass("NSURLSession"),
              @selector(dataTaskWithRequest:completionHandler:),
              (IMP)sg_task, (IMP *)&o_task);
}
