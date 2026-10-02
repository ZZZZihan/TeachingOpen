package org.jeecg.modules.message.websocket;

import com.alibaba.fastjson.JSONObject;
import lombok.extern.slf4j.Slf4j;
import org.jeecg.common.constant.WebsocketConst;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.common.util.SpringContextUtils;
import org.jeecg.modules.shiro.authc.ShiroRealm;
import org.springframework.stereotype.Component;

import javax.websocket.CloseReason;
import javax.websocket.OnClose;
import javax.websocket.OnError;
import javax.websocket.OnMessage;
import javax.websocket.OnOpen;
import javax.websocket.Session;
import javax.websocket.server.PathParam;
import javax.websocket.server.ServerEndpoint;
import java.io.IOException;
import java.util.concurrent.CopyOnWriteArraySet;

/** Notification subscriptions are registered only after authenticating the first frame. */
@Component
@Slf4j
@ServerEndpoint("/websocket/{userId}")
public class WebSocket {
    private static final CopyOnWriteArraySet<WebSocket> subscribers = new CopyOnWriteArraySet<>();
    private Session session;
    private String requestedUserId;
    private volatile String userId;
    private String token;
    private boolean closed;

    @OnOpen
    public void onOpen(Session session, @PathParam("userId") String requestedUserId) {
        this.session = session;
        this.requestedUserId = requestedUserId;
        session.setMaxTextMessageBufferSize(8192);
        session.setMaxIdleTimeout(10000);
    }

    @OnMessage
    public synchronized void onMessage(String message) {
        if (closed) return;
        try {
            if (token == null) {
                JSONObject auth = JSONObject.parseObject(message);
                if (auth == null || !"authenticate".equals(auth.getString("type"))) {
                    reject();
                    return;
                }
                String credential = auth.getString("token");
                if (credential == null || credential.isEmpty() || credential.length() > 4096) {
                    reject();
                    return;
                }
                LoginUser user = realm().checkUserTokenIsEffect(credential);
                if (user == null || !user.getId().equals(requestedUserId)) {
                    reject();
                    return;
                }
                token = credential;
                userId = user.getId();
                session.setMaxIdleTimeout(60000);
                subscribers.add(this);
                JSONObject reply = new JSONObject();
                reply.put("cmd", "authenticated");
                // The credential never appears in a URL, acknowledgement or log.
                session.getAsyncRemote().sendText(reply.toJSONString());
            } else if ("HeartBeat".equals(message) && active()) {
                JSONObject reply = new JSONObject();
                reply.put(WebsocketConst.MSG_CMD, WebsocketConst.CMD_CHECK);
                reply.put(WebsocketConst.MSG_TXT, "心跳响应");
                session.getAsyncRemote().sendText(reply.toJSONString());
            } else {
                reject();
            }
        } catch (RuntimeException failure) {
            // Invalid payloads, credentials and unavailable authentication fail closed.
            reject();
        }
    }

    private ShiroRealm realm() {
        return SpringContextUtils.getBean(ShiroRealm.class);
    }

    private boolean active() {
        if (session == null || !session.isOpen() || token == null || userId == null) {
            reject();
            return false;
        }
        try {
            LoginUser current = realm().checkUserTokenIsEffect(token);
            if (current != null && userId.equals(current.getId())) return true;
        } catch (RuntimeException failure) {
            // Logout/expiry and authentication failures stop subsequent delivery.
        }
        reject();
        return false;
    }

    private synchronized void deliver(String message) {
        if (!active()) return;
        try {
            session.getAsyncRemote().sendText(message, result -> {
                if (!result.isOK()) reject();
            });
        } catch (RuntimeException failure) {
            reject();
        }
    }

    private synchronized void reject() {
        closed = true;
        subscribers.remove(this);
        token = null;
        userId = null;
        if (session != null && session.isOpen()) {
            try {
                session.close(new CloseReason(CloseReason.CloseCodes.VIOLATED_POLICY, "Notification session unavailable"));
            } catch (IOException ignored) {
                log.debug("Notification connection already unavailable");
            }
        }
    }

    @OnClose
    public synchronized void onClose() {
        closed = true;
        subscribers.remove(this);
        token = null;
        userId = null;
    }

    @OnError
    public void onError(Throwable failure) {
        reject();
    }

    public void sendAllMessage(String message) {
        for (WebSocket subscriber : subscribers) subscriber.deliver(message);
    }

    public void sendOneMessage(String targetUserId, String message) {
        if (targetUserId == null) return;
        for (WebSocket subscriber : subscribers) {
            if (targetUserId.equals(subscriber.userId)) subscriber.deliver(message);
        }
    }

    public void sendMoreMessage(String[] userIds, String message) {
        if (userIds == null) return;
        for (String targetUserId : userIds) sendOneMessage(targetUserId, message);
    }
}
