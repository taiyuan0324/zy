/**
 * 汽水音乐 去广告与激励视频静默优化
 * 移除破坏签名的请求体篡改，确保 100% 成功结算
 */

const url = $request.url;
let body = $response.body;

if (body) {
    try {
        let obj = JSON.parse(body);

        // 1. 清除开屏广告
        if (url.includes("/luna/advert/splash/brand/retrieve")) {
            obj.launches = [];
            $done({ body: JSON.stringify(obj) });
            return;
        }

        // 2. 移除歌曲信息流中的推广卡片
        if (url.includes("/luna/card") || url.includes("/feed/")) {
            if (Array.isArray(obj.card_items)) {
                obj.card_items = obj.card_items.filter(item => item.type !== "advert" && item.type !== "ad");
            }
            $done({ body: JSON.stringify(obj) });
            return;
        }

        $done({});
    } catch (e) {
        $done({});
    }
} else {
    $done({});
}
