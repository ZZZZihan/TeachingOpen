import org.apache.shiro.web.filter.InvalidRequestFilter;
import javax.servlet.*;
import javax.servlet.http.*;
import java.lang.reflect.*;
import java.net.URLEncoder;
import java.util.*;

/** Exact candidate filter, synthetic servlet fields only; no application context or network. */
public final class UnicodeFilterMatrix {
    private static final String PREFIX = "/sys/common/static/";
    private static final List<Case> cases = new ArrayList<Case>();
    private static final class Case {
        String id, context, uri, servlet, info, method;
        DispatcherType dispatcher;
        boolean expected, strictExpected;
        Map<String,Object> attributes = new HashMap<String,Object>();
        Case(String id, String context, String uri, String servlet, String info, String method,
             DispatcherType dispatcher, boolean expected, boolean strictExpected) {
            this.id=id; this.context=context; this.uri=uri; this.servlet=servlet; this.info=info;
            this.method=method; this.dispatcher=dispatcher; this.expected=expected; this.strictExpected=strictExpected;
        }
    }
    private static String encoded(String path) throws Exception {
        StringBuilder out = new StringBuilder();
        for (String p:path.split("/",-1)) {
            if (out.length()>0 || path.startsWith("/")) out.append('/');
            out.append(URLEncoder.encode(p,"UTF-8").replace("+","%20"));
        }
        // Paths passed here start with '/', whose empty first segment was already emitted.
        return path.startsWith("/") ? out.substring(1) : out.toString();
    }
    private static void add(String id, String uri, String servlet, String info, String method,
                            DispatcherType dispatcher, boolean expected, boolean strictExpected) {
        cases.add(new Case(id,"/api",uri,servlet,info,method,dispatcher,expected,strictExpected));
    }
    private static void unicode(String id,String path,String method,DispatcherType dispatcher,boolean allow) throws Exception {
        add(id,encoded("/api"+path),path,null,method,dispatcher,allow,false);
    }
    private static Object primitiveDefault(Class<?> type) {
        if (!type.isPrimitive()) return null;
        if (type==boolean.class) return false;
        if (type==int.class) return 0;
        if (type==long.class) return 0L;
        if (type==double.class) return 0D;
        if (type==float.class) return 0F;
        if (type==short.class) return (short)0;
        if (type==byte.class) return (byte)0;
        if (type==char.class) return (char)0;
        return null;
    }
    private static HttpServletRequest request(final Case c) {
        return (HttpServletRequest) Proxy.newProxyInstance(UnicodeFilterMatrix.class.getClassLoader(),
            new Class<?>[]{HttpServletRequest.class}, (proxy,method,args) -> {
                String n=method.getName();
                if (n.equals("getRequestURI")) return c.uri;
                if (n.equals("getServletPath")) return c.servlet;
                if (n.equals("getPathInfo")) return c.info;
                if (n.equals("getContextPath")) return c.context;
                if (n.equals("getMethod")) return c.method;
                if (n.equals("getDispatcherType")) return c.dispatcher;
                if (n.equals("getAttribute")) return c.attributes.get((String)args[0]);
                if (n.equals("getAttributeNames")) return Collections.enumeration(c.attributes.keySet());
                if (n.equals("getCharacterEncoding")) return "UTF-8";
                if (n.equals("toString")) return "synthetic:"+c.id;
                if (n.equals("hashCode")) return System.identityHashCode(proxy);
                if (n.equals("equals")) return proxy==args[0];
                return primitiveDefault(method.getReturnType());
            });
    }
    private static String q(String value) {
        if (value==null) return "null";
        StringBuilder b=new StringBuilder("\"");
        for (char c:value.toCharArray()) {
            if (c=='\\' || c=='\"') b.append('\\').append(c);
            else if (c<32) b.append(String.format("\\u%04x",(int)c));
            else b.append(c);
        }
        return b.append('"').toString();
    }
    public static void main(String[] args) throws Exception {
        String chinese=PREFIX+"课程/课件.pdf";
        unicode("canonical_encoded_chinese_get",chinese,"GET",DispatcherType.REQUEST,true);
        unicode("canonical_encoded_chinese_head",chinese,"HEAD",DispatcherType.REQUEST,true);
        unicode("literal_unicode_fields_synthetic",chinese,"GET",DispatcherType.REQUEST,true);
        cases.get(cases.size()-1).uri="/api"+chinese;
        unicode("mixed_unicode_space_plus_percent",PREFIX+"单元 空格/课+件50%.pdf","GET",DispatcherType.REQUEST,true);
        unicode("unicode_literal_fullwidth_slash_is_filename",PREFIX+"课／件.pdf","GET",DispatcherType.REQUEST,true);
        unicode("unicode_combining_name_no_normalization",PREFIX+"课程/e\u0301.pdf","GET",DispatcherType.REQUEST,true);
        unicode("split_servlet_mapping",chinese,"GET",DispatcherType.REQUEST,true);
        cases.get(cases.size()-1).servlet="/sys/common/static";
        cases.get(cases.size()-1).info="/课程/课件.pdf";
        Case noContext=new Case("empty_context_canonical","",encoded(chinese),chinese,null,"GET",DispatcherType.REQUEST,true,false);
        cases.add(noContext);
        for (String method:new String[]{"POST","PUT","DELETE","OPTIONS"}) unicode("unicode_method_"+method,chinese,method,DispatcherType.REQUEST,false);
        for (DispatcherType d:new DispatcherType[]{DispatcherType.FORWARD,DispatcherType.INCLUDE,DispatcherType.ERROR,DispatcherType.ASYNC}) unicode("unicode_dispatch_"+d,chinese,"GET",d,false);
        unicode("nonmedia_unicode", "/teaching/课程", "GET",DispatcherType.REQUEST,false);
        unicode("lookalike_media_prefix", "/sys/common/static-other/课程.pdf", "GET",DispatcherType.REQUEST,false);
        unicode("wrong_raw_route",chinese,"GET",DispatcherType.REQUEST,false);
        cases.get(cases.size()-1).uri=encoded("/api/other/课程.pdf");
        unicode("wrong_decoded_route",chinese,"GET",DispatcherType.REQUEST,false);
        cases.get(cases.size()-1).servlet="/other/课程.pdf";
        unicode("encoded_structural_prefix",chinese,"GET",DispatcherType.REQUEST,false);
        cases.get(cases.size()-1).uri=encoded("/api"+chinese).replace("/sys/","/%73ys/");
        unicode("context_prefix_boundary",chinese,"GET",DispatcherType.REQUEST,false);
        cases.get(cases.size()-1).uri=encoded("/apix"+chinese);
        unicode("missing_servlet_path",chinese,"GET",DispatcherType.REQUEST,false);
        cases.get(cases.size()-1).servlet=null;
        cases.get(cases.size()-1).info=chinese;
        for (char c:new char[]{0,9,10,13,31,127,128,133,159}) unicode("control_decoded_"+(int)c,PREFIX+"课"+c+"件.pdf","GET",DispatcherType.REQUEST,false);
        unicode("control_raw_uri",chinese,"GET",DispatcherType.REQUEST,false);
        cases.get(cases.size()-1).uri="/api"+chinese+'\u0085';
        unicode("control_path_info",chinese,"GET",DispatcherType.REQUEST,false);
        cases.get(cases.size()-1).servlet="/sys/common/static";
        cases.get(cases.size()-1).info="/课程/课\u007f件.pdf";
        for (String suffix:new String[]{"课;件.pdf","课\\件.pdf","./课件.pdf","../课件.pdf","目录/../课件.pdf","目录/./课件.pdf"}) unicode("structural_decoded_"+cases.size(),PREFIX+suffix,"GET",DispatcherType.REQUEST,false);
        for (String encodedPart:new String[]{"%3B","%3b","%5C","%5c","%2E","%2e","%2F","%2f"}) {
            unicode("structural_raw_"+encodedPart,chinese,"GET",DispatcherType.REQUEST,false);
            cases.get(cases.size()-1).uri=encoded("/api"+chinese)+encodedPart;
        }
        unicode("double_encoded_dot_slash",PREFIX+"%2e%2e%2f课件.pdf","GET",DispatcherType.REQUEST,false);
        unicode("duplicate_separator_preserves_upstream_behavior",PREFIX+"目录//课件.pdf","GET",DispatcherType.REQUEST,true);
        for (String path:new String[]{PREFIX+"ordinary.pdf",PREFIX+"space name.pdf",PREFIX+"plus+name.pdf",PREFIX+"50%name.pdf","/teaching/course","/v2/api-docs","/actuator/metrics"}) {
            add("ascii_equivalence_"+cases.size(),encoded("/api"+path),path,null,"GET",DispatcherType.REQUEST,true,true);
        }
        for (DispatcherType d:DispatcherType.values()) add("ascii_dispatch_equivalence_"+d,"/api"+PREFIX+"ordinary.pdf",PREFIX+"ordinary.pdf",null,"GET",d,true,true);
        add("ascii_post_filter_equivalence_not_method_authorization","/api"+PREFIX+"ordinary.pdf",PREFIX+"ordinary.pdf",null,"POST",DispatcherType.REQUEST,true,true);
        for (String path:new String[]{"/v2/api-docs;matrix","/actuator/metrics\\matrix","/a/../b","/a/./b","/a/%2e/b","/a/%2f/b"}) add("ascii_invalid_equivalence_"+cases.size(),"/api"+path,path,null,"GET",DispatcherType.REQUEST,false,false);
        Case included=new Case("include_attributes_preserve_original_getter_scope","/api","/api/public/plain","/public/plain",null,"GET",DispatcherType.INCLUDE,true,true);
        included.attributes.put("javax.servlet.include.request_uri",encoded("/api"+chinese));
        included.attributes.put("javax.servlet.include.servlet_path",chinese);
        cases.add(included);
        Class<?> candidateType=Class.forName("org.jeecg.modules.shiro.authc.aop.LocalMediaInvalidRequestFilter");
        Object candidate=candidateType.newInstance();
        InvalidRequestFilter strict=new InvalidRequestFilter();
        Method candidateMethod=candidateType.getDeclaredMethod("isAccessAllowed",ServletRequest.class,ServletResponse.class,Object.class);
        Method strictMethod=InvalidRequestFilter.class.getDeclaredMethod("isAccessAllowed",ServletRequest.class,ServletResponse.class,Object.class);
        candidateMethod.setAccessible(true); strictMethod.setAccessible(true);
        List<String> records=new ArrayList<String>();
        int passed=0;
        for (Case c:cases) {
            HttpServletRequest request=request(c);
            boolean actual=(Boolean)candidateMethod.invoke(candidate,request,null,null);
            boolean original=(Boolean)strictMethod.invoke(strict,request,null,null);
            boolean ok=actual==c.expected && original==c.strictExpected;
            if (ok) passed++;
            records.add("{\"case\":"+q(c.id)+",\"dispatcher\":"+q(c.dispatcher.name())+",\"method\":"+q(c.method)+",\"candidate\":"+actual+",\"expected\":"+c.expected+",\"original\":"+original+",\"original_expected\":"+c.strictExpected+",\"passed\":"+ok+"}");
        }
        boolean outerDefaults=((InvalidRequestFilter)candidate).isBlockNonAscii()
                && ((InvalidRequestFilter)candidate).isBlockSemicolon() && ((InvalidRequestFilter)candidate).isBlockTraversal()
                && ((InvalidRequestFilter)candidate).isBlockEncodedPeriod() && ((InvalidRequestFilter)candidate).isBlockEncodedForwardSlash()
                && ((InvalidRequestFilter)candidate).isBlockRewriteTraversal();
        final int[] deniedStatus={0};
        HttpServletResponse response=(HttpServletResponse)Proxy.newProxyInstance(UnicodeFilterMatrix.class.getClassLoader(),new Class<?>[]{HttpServletResponse.class},(proxy,method,values)->{
            if(method.getName().equals("sendError")) deniedStatus[0]=(Integer)values[0];
            return primitiveDefault(method.getReturnType());
        });
        Method deny=InvalidRequestFilter.class.getDeclaredMethod("onAccessDenied",ServletRequest.class,ServletResponse.class);
        deny.setAccessible(true);
        boolean deniedResult=(Boolean)deny.invoke(candidate,request(cases.get(0)),response);
        boolean denialContract=deniedStatus[0]==400 && !deniedResult;
        System.out.println("{\"scope\":\"Real exact-JAR filter with synthetic servlet proxy; no container routing, database, cache, login, server or file-byte acceptance\",\"outer_default_guards\":"+outerDefaults+",\"native_denial_400\":"+denialContract+",\"passed\":"+passed+",\"total\":"+cases.size()+",\"cases\":["+String.join(",",records)+"]}");
        if(passed!=cases.size() || !outerDefaults || !denialContract) System.exit(1);
    }
}
