/**
 * 汽水音乐 VIP 时长秒过 & 激励广告优化脚本
 * 适用: Loon (HTTP-Response & HTTP-Request)
 * 基于官方 21.1.0 抓包接口 (beta-luna.douyin.com & api.qishui.com) 定制
 */

const url = $request.url;

// 1. 拦截激励视频下发，将 30 秒倒计时压缩为 1 秒并开启跳过
if (url.includes("/luna/advert/incentive/retrieve")) {
    let body = $response.body;
    if (body) {
        try {
            let obj = JSON.parse(body);
            if (obj.ad_infos_map) {
                for (let k in obj.ad_infos_map) {
                    let group = obj.ad_infos_map[k];
                    if (group && Array.isArray(group.ad_infos)) {
                        group.ad_infos.forEach(ad => {
                            ad.launch_duration = 1; // 欺骗播放器仅需播放1秒
                            if (ad.component) {
                                ad.component.countdown = {
                                    can_skip: true,
                                    skip_duration: 0
                                };
                            }
                        });
                    }
                }
            }
            if (Array.isArray(obj.ad_infos)) {
                obj.ad_infos.forEach(ad => {
                    ad.launch_duration = 1;
                });
            }
            $done({ body: JSON.stringify(obj) });
        } catch (e) {
            $done({});
        }
    } else {
        $done({});
    }
}

// 2. 完播上报校准：欺骗服务端播放完整了 30 秒，确保通过入账校验
else if (url.includes("/luna/advert/incentive/done") && $request.body) {
    try {
        let reqObj = JSON.parse($request.body);
        reqObj.launch_duration = 30; // 维持合规值，确保成功写入时长
        $done({ body: JSON.stringify(reqObj) });
    } catch (e) {
        $done({});
    }
}

// 3. 修改全局激励配置：缩短 feed 广告倒计时并解除首滑限制
else if (url.includes("/luna/advert/incentive/config")) {
    let body = $response.body;
    if (body) {
        try {
            let obj = JSON.parse(body);
            if (obj.feed_advert_config) {
                obj.feed_advert_config.advert_duration = 1;
                obj.feed_advert_config.forbid_first_slide = false;
            }
            $done({ body: JSON.stringify(obj) });
        } catch (e) {
            $done({});
        }
    } else {
        $done({});
    }
}

// 4. 清理开屏与弹窗广告
else if (url.includes("/luna/advert/splash/brand/retrieve")) {
    let body = $response.body;
    if (body) {
        try {
            let obj = JSON.parse(body);
            obj.launches = [];
            $done({ body: JSON.stringify(obj) });
        } catch (e) {
            $done({});
        }
    } else {
        $done({});
    }
} else {
    $done({});
}
