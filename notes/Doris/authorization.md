### stream load authorization
```bash
curl  --location-trusted -u root: -T $doris_workspace/data_src/test.csv -H "column_separator:," http://127.0.0.1:5937/ap    i/demo/et1/_stream_load
```
需要在 http request header 中添加 Authorization，这部分在 FE 被解析：
```java
public RedirectView redirectTo(HttpServletRequest request, TNetworkAddress addr) {
        URI urlObj = null;
        URI resultUriObj = null;
        String urlStr = request.getRequestURI();
        String userInfo = null;
        if (!Strings.isNullOrEmpty(request.getHeader("Authorization"))) {
            ActionAuthorizationInfo authInfo = getAuthorizationInfo(request);
        }
}

public ActionAuthorizationInfo getAuthorizationInfo(HttpServletRequest request)
            throws UnauthorizedException {
    ActionAuthorizationInfo authInfo = new ActionAuthorizationInfo();
    if (!parseAuthInfo(request, authInfo)) {
        LOG.info("parse auth info failed, Authorization header {}, url {}",
                request.getHeader("Authorization"), request.getRequestURI());
        throw new UnauthorizedException("Need auth information.");
    }
    LOG.debug("get auth info: {}", authInfo);
    return authInfo;
}

private boolean parseAuthInfo(HttpServletRequest request, ActionAuthorizationInfo authInfo) {
    String encodedAuthString = request.getHeader("Authorization");
    if (Strings.isNullOrEmpty(encodedAuthString)) {
        return false;
    }
    ...
}
```
