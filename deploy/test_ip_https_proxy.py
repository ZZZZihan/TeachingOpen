#!/usr/bin/env python3
"""Exercise real Boot binding -> Tomcat RemoteIpValve -> source MediaCookie.

Requires an existing Java 8 JDK and populated project Maven cache; installs
nothing. No application context, database, service, socket or external request
is opened. Synthetic Tomcat requests exercise the real valve and cookie code.
Run: python3 deploy/test_ip_https_proxy.py --java-home <jdk> --m2 <cache>
This does not replace a deployed HTTPS login and bind-address verification.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile


ROOT = Path(__file__).resolve().parents[1]
FRAGMENT = ROOT / 'deploy/ip-https-proxy.properties.example'
COOKIE = ROOT / 'api/jeecg-boot-module-system/src/main/java/org/jeecg/modules/shiro/authc/aop/MediaCookie.java'
HARNESS = r'''
import java.io.*;
import java.lang.reflect.Field;
import java.util.*;
import org.apache.catalina.Valve;
import org.apache.catalina.connector.*;
import org.apache.catalina.valves.*;
import org.springframework.boot.autoconfigure.web.ServerProperties;
import org.springframework.boot.autoconfigure.web.embedded.TomcatWebServerFactoryCustomizer;
import org.springframework.boot.context.properties.bind.*;
import org.springframework.boot.web.embedded.tomcat.TomcatServletWebServerFactory;
import org.springframework.core.env.*;
import org.jeecg.modules.shiro.authc.aop.MediaCookie;

public class IpHttpsProxyProbe {
    static int passed;
    static void check(boolean value, String label) {
        if (!value) throw new AssertionError(label);
        System.out.println("PASS " + label);
        passed++;
    }

    static RemoteIpValve configuredValve(String path) throws Exception {
        Properties properties = new Properties();
        try (InputStream input = new FileInputStream(path)) { properties.load(input); }
        StandardEnvironment environment = new StandardEnvironment();
        // Bind only the tested fragment, without ambient shell/system overrides.
        List<String> ambientSources = new ArrayList<>();
        environment.getPropertySources().forEach(source -> ambientSources.add(source.getName()));
        for (String source : ambientSources) environment.getPropertySources().remove(source);
        environment.getPropertySources().addFirst(new PropertiesPropertySource("https-fragment", properties));
        ServerProperties server = Binder.get(environment).bind("server", Bindable.of(ServerProperties.class)).get();
        check("127.0.0.1".equals(server.getAddress().getHostAddress()), "Boot binds IPv4 loopback address");
        check(Boolean.TRUE.equals(server.isUseForwardHeaders()), "Boot binds forwarded-header opt in");
        TomcatServletWebServerFactory factory = new TomcatServletWebServerFactory();
        new TomcatWebServerFactoryCustomizer(environment, server).customize(factory);
        List<RemoteIpValve> valves = new ArrayList<>();
        for (Valve valve : factory.getEngineValves()) if (valve instanceof RemoteIpValve) valves.add((RemoteIpValve)valve);
        check(valves.size() == 1, "Boot creates one real RemoteIpValve");
        RemoteIpValve valve = valves.get(0);
        check("^127[.]0[.]0[.]1$".equals(valve.getInternalProxies()) && valve.getTrustedProxies() == null,
              "customizer narrows proxy trust without extra trusted proxies");
        check("X-Forwarded-For".equals(valve.getRemoteIpHeader())
              && "X-Forwarded-Proto".equals(valve.getProtocolHeader())
              && "X-Forwarded-Port".equals(valve.getPortHeader())
              && "https".equals(valve.getProtocolHeaderHttpsValue()), "real valve receives all supported header bindings");
        return valve;
    }

    static void probe(RemoteIpValve valve, MediaCookie cookie, String peer, String protocol,
                      boolean secure, int expectedPort, boolean clear) throws Exception {
        Connector connector = new Connector();
        org.apache.coyote.Request wire = new org.apache.coyote.Request();
        wire.scheme().setString("http");
        wire.serverName().setString("192.0.2.20");
        wire.setServerPort(8080);
        wire.remoteAddr().setString(peer);
        wire.remoteHost().setString(peer);
        wire.localName().setString("localhost");
        wire.localAddr().setString("127.0.0.1");
        wire.setLocalPort(8080);
        wire.method().setString("GET");
        wire.requestURI().setString("/api/probe");
        wire.getMimeHeaders().setValue("X-Forwarded-For").setString("198.51.100.21");
        wire.getMimeHeaders().setValue("X-Forwarded-Port").setString("http".equals(protocol) ? "80" : "443");
        wire.getMimeHeaders().setValue("X-Forwarded-Host").setString("forged.invalid");
        if (protocol != null) wire.getMimeHeaders().setValue("X-Forwarded-Proto").setString(protocol);
        // Only the context path is supplied by the fixture. Header, peer,
        // scheme, port and isSecure behavior all remain real Tomcat code.
        Request request = new Request(connector) {
            public String getContextPath() { return "/api"; }
        };
        request.setCoyoteRequest(wire);
        request.setRemoteAddr(peer);
        request.setRemoteHost(peer);
        Response response = new Response();
        response.setCoyoteResponse(new org.apache.coyote.Response());
        response.setRequest(request);
        request.setResponse(response);
        final boolean[] called = {false};
        valve.setNext(new ValveBase() {
            public void invoke(Request actual, Response result) {
                if (actual.isSecure() != secure || !actual.getScheme().equals(secure ? "https" : "http"))
                    throw new AssertionError("scheme/secure mismatch for " + peer + "/" + protocol);
                if (actual.getServerPort() != expectedPort) throw new AssertionError("port mismatch");
                if (!"192.0.2.20".equals(actual.getServerName())) throw new AssertionError("unsupported forwarded host changed server name");
                String expectedRemote = peer.equals("127.0.0.1") ? "198.51.100.21" : peer;
                if (!expectedRemote.equals(actual.getRemoteAddr())) throw new AssertionError("remote IP trust mismatch");
                cookie.write(actual, result, "synthetic-not-a-login-token", clear);
                called[0] = true;
            }
        });
        valve.invoke(request, response);
        String header = response.getHeader("Set-Cookie");
        check(called[0] && header != null && header.contains("; Secure") == secure
              && header.contains("; HttpOnly; SameSite=Strict")
              && header.contains("; Path=/api/sys/common/static")
              && header.contains("; Max-Age=0") == clear
              && "no-store".equals(response.getHeader("Cache-Control")),
              peer + " protocol=" + protocol + " secure=" + secure + " clear=" + clear);
    }

    public static void main(String[] args) throws Exception {
        RemoteIpValve valve = configuredValve(args[0]);
        MediaCookie cookie = new MediaCookie();
        Field name = MediaCookie.class.getDeclaredField("name");
        name.setAccessible(true); name.set(cookie, "teaching_media_test");
        probe(valve, cookie, "127.0.0.1", "https", true, 443, false);
        probe(valve, cookie, "127.0.0.1", "https", true, 443, true);
        probe(valve, cookie, "127.0.0.1", "http", false, 80, false);
        probe(valve, cookie, "127.0.0.1", null, false, 8080, false);
        for (String peer : Arrays.asList("203.0.113.8", "10.0.0.8", "192.168.1.8", "127.0.0.2", "::1"))
            probe(valve, cookie, peer, "https", false, 8080, false);
        System.out.println("RESULT " + passed + " checks passed; no server started");
    }
}
'''


def jar(cache, group, artifact, version):
    path = cache / group.replace('.', '/') / artifact / version / f'{artifact}-{version}.jar'
    if not path.is_file():
        raise RuntimeError(f'Missing existing dependency: {path}; populate the normal project cache first')
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--java-home', required=True, type=Path)
    parser.add_argument('--m2', required=True, type=Path)
    args = parser.parse_args()
    ns = {'m': 'http://maven.apache.org/POM/4.0.0'}
    pom = ET.parse(ROOT / 'api/pom.xml').getroot()
    boot = pom.find('m:parent/m:version', ns).text
    tomcat = pom.find('m:properties/m:tomcat.version', ns).text
    if boot != '2.1.3.RELEASE':
        raise RuntimeError('Review proxy property bindings for the changed Spring Boot version')
    jars = [jar(args.m2, 'org.springframework.boot', item, boot)
            for item in ('spring-boot', 'spring-boot-autoconfigure')]
    with zipfile.ZipFile(jars[1]) as archive:
        metadata = json.loads(archive.read('META-INF/spring-configuration-metadata.json'))
    supported = {item['name'] for item in metadata['properties']}
    configured = [line.split('=', 1)[0] for line in FRAGMENT.read_text().splitlines()
                  if line and not line.startswith('#')]
    unsupported = set(configured) - supported
    if unsupported:
        raise RuntimeError('Properties unsupported by the actual Boot JAR: ' + ', '.join(sorted(unsupported)))
    print(f'PASS all {len(configured)} properties exist in Boot {boot} metadata; Tomcat {tomcat}', flush=True)
    jars += [jar(args.m2, 'org.apache.tomcat.embed', 'tomcat-embed-core', tomcat)]
    jars += [jar(args.m2, 'org.springframework', item, '5.1.5.RELEASE')
             for item in ('spring-core', 'spring-jcl', 'spring-beans', 'spring-context', 'spring-expression', 'spring-web')]
    with tempfile.TemporaryDirectory(prefix='teachingopen-ip-https-proxy-') as directory:
        scratch = Path(directory)
        source = scratch / 'IpHttpsProxyProbe.java'
        source.write_text(HARNESS)
        classpath = os.pathsep.join(map(str, jars))
        subprocess.run([str(args.java_home / 'bin/javac'), '-encoding', 'UTF-8', '-cp', classpath,
                        '-d', directory, str(COOKIE), str(source)], check=True, timeout=60)
        subprocess.run([str(args.java_home / 'bin/java'), '-cp', directory + os.pathsep + classpath,
                        'IpHttpsProxyProbe', str(FRAGMENT)], check=True, timeout=60)


if __name__ == '__main__':
    main()
