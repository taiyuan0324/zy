// seagull.m — 汽水音乐 21.x 自签名包补丁 (v2)
//
// v1 事故复盘（卡启动界面 / 没网络），v2 全部移除：
//   1. hook NSURLSession dataTaskWithRequest:completionHandler:
//      → 启动期关键请求被包装/吞掉，App 网络全废。且新版 API 走 Cronet，本就无效。
//   2. hook UIWindow setRootViewController:
//      → 一旦误判，rootVC 永远不被设置，界面直接卡在 LaunchScreen。
//   3. SGIsAntiCheat 匹配 "STSecurity"
//      → STSecurity 模块下所有页面（隐私设置等）都被误拦，范围过宽。
//   4. present 被拦时没调 completion → 调用方永远等回调，流程 hang。
//
// v2 原则：只拦一个明确类名，只吞 present/push，拦截必调 completion，
//          零网络侵入，安装延后到主线程，避开 dyld constructor 阶段。

#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#import <objc/runtime.h>

#pragma mark - 判定（收紧：只认 AntiCheatViewController 这一类）

static BOOL SGIsAntiCheat(id vc) {
    if (!vc) return NO;
    NSString *n = NSStringFromClass([vc class]);
    if (!n) return NO;
    return [n rangeOfString:@"AntiCheatViewController"].location != NSNotFound;
}

#pragma mark - 原函数指针

typedef void (*PresentFn)(id, SEL, id, BOOL, id);
typedef void (*PushFn)(id, SEL, id, BOOL);

static PresentFn o_present;
static PushFn    o_push;

#pragma mark - Hook 实现

static void sg_present(id self, SEL _cmd, UIViewController *vc, BOOL anim, void (^done)(void)) {
    if (SGIsAntiCheat(vc)) {
        NSLog(@"[SG v2] blocked present %@", NSStringFromClass([vc class]));
        // 关键：必须回调 completion，否则调用方会一直等待 → 启动流程 hang
        if (done) done();
        return;
    }
    if (o_present) o_present(self, _cmd, vc, anim, (id)done);
}

static void sg_push(id self, SEL _cmd, UIViewController *vc, BOOL anim) {
    if (SGIsAntiCheat(vc)) {
        NSLog(@"[SG v2] blocked push %@", NSStringFromClass([vc class]));
        return;
    }
    if (o_push) o_push(self, _cmd, vc, anim);
}

#pragma mark - 安装

static void SGInstall(Class cls, SEL sel, IMP imp, IMP *slot) {
    if (!cls || !sel) return;
    Method m = class_getInstanceMethod(cls, sel);
    if (!m) {
        NSLog(@"[SG v2] method not found: %@", NSStringFromSelector(sel));
        return;
    }
    // class_replaceMethod 原子返回原 IMP，比 getImplementation + setImplementation 稳
    IMP old = class_replaceMethod(cls, sel, imp, method_getTypeEncoding(m));
    *slot = old ? old : method_getImplementation(m);
    NSLog(@"[SG v2] hooked %@.%@", NSStringFromClass(cls), NSStringFromSelector(sel));
}

__attribute__((constructor))
static void SGEntry(void) {
    NSLog(@"[SG v2] seagull loaded (%s) — 只拦弹窗，零网络侵入", __DATE__);
    // 延后到主线程：避开 dyld constructor 阶段 UIKit 尚未就绪的风险
    dispatch_async(dispatch_get_main_queue(), ^{
        SGInstall(objc_getClass("UIViewController"),
                  @selector(presentViewController:animated:completion:),
                  (IMP)sg_present, (IMP *)&o_present);
        SGInstall(objc_getClass("UINavigationController"),
                  @selector(pushViewController:animated:),
                  (IMP)sg_push, (IMP *)&o_push);
        NSLog(@"[SG v2] install done");
    });
}
