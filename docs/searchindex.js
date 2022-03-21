Search.setIndex({docnames:["api/auth","api/common","api/eventstream","api/exceptions","api/http","api/io","api/mqtt","api/s3","index"],envversion:{"sphinx.domains.c":2,"sphinx.domains.changeset":1,"sphinx.domains.citation":1,"sphinx.domains.cpp":4,"sphinx.domains.index":1,"sphinx.domains.javascript":2,"sphinx.domains.math":2,"sphinx.domains.python":3,"sphinx.domains.rst":2,"sphinx.domains.std":2,sphinx:56},filenames:["api/auth.rst","api/common.rst","api/eventstream.rst","api/exceptions.rst","api/http.rst","api/io.rst","api/mqtt.rst","api/s3.rst","index.rst"],objects:{"awscrt.auth":[[0,1,1,"","AwsCredentials"],[0,1,1,"","AwsCredentialsProvider"],[0,1,1,"","AwsSignatureType"],[0,1,1,"","AwsSignedBodyHeaderType"],[0,1,1,"","AwsSignedBodyValue"],[0,1,1,"","AwsSigningAlgorithm"],[0,1,1,"","AwsSigningConfig"],[0,5,1,"","aws_sign_request"]],"awscrt.auth.AwsCredentials":[[0,2,1,"","access_key_id"],[0,2,1,"","expiration"],[0,2,1,"","secret_access_key"],[0,2,1,"","session_token"]],"awscrt.auth.AwsCredentialsProvider":[[0,3,1,"","get_credentials"],[0,3,1,"","new_chain"],[0,3,1,"","new_default_chain"],[0,3,1,"","new_delegate"],[0,3,1,"","new_environment"],[0,3,1,"","new_process"],[0,3,1,"","new_profile"],[0,3,1,"","new_static"]],"awscrt.auth.AwsSignatureType":[[0,2,1,"","HTTP_REQUEST_HEADERS"],[0,2,1,"","HTTP_REQUEST_QUERY_PARAMS"]],"awscrt.auth.AwsSignedBodyHeaderType":[[0,2,1,"","NONE"],[0,2,1,"","X_AMZ_CONTENT_SHA_256"]],"awscrt.auth.AwsSignedBodyValue":[[0,2,1,"","EMPTY_SHA256"],[0,2,1,"","STREAMING_AWS4_HMAC_SHA256_EVENTS"],[0,2,1,"","STREAMING_AWS4_HMAC_SHA256_PAYLOAD"],[0,2,1,"","UNSIGNED_PAYLOAD"]],"awscrt.auth.AwsSigningAlgorithm":[[0,2,1,"","V4"],[0,2,1,"","V4_ASYMMETRIC"]],"awscrt.auth.AwsSigningConfig":[[0,4,1,"","algorithm"],[0,4,1,"","credentials_provider"],[0,4,1,"","date"],[0,4,1,"","expiration_in_seconds"],[0,4,1,"","omit_session_token"],[0,4,1,"","region"],[0,3,1,"","replace"],[0,4,1,"","service"],[0,4,1,"","should_normalize_uri_path"],[0,4,1,"","should_sign_header"],[0,4,1,"","signature_type"],[0,4,1,"","signed_body_header_type"],[0,4,1,"","signed_body_value"],[0,4,1,"","use_double_uri_encode"]],"awscrt.common":[[1,5,1,"","get_cpu_count_for_group"],[1,5,1,"","get_cpu_group_count"]],"awscrt.eventstream":[[2,1,1,"","Header"],[2,1,1,"","HeaderType"],[2,0,0,"-","rpc"]],"awscrt.eventstream.Header":[[2,3,1,"","from_bool"],[2,3,1,"","from_byte"],[2,3,1,"","from_byte_buf"],[2,3,1,"","from_int16"],[2,3,1,"","from_int32"],[2,3,1,"","from_int64"],[2,3,1,"","from_string"],[2,3,1,"","from_timestamp"],[2,3,1,"","from_uuid"],[2,4,1,"","name"],[2,4,1,"","type"],[2,4,1,"","value"],[2,3,1,"","value_as_bool"],[2,3,1,"","value_as_byte"],[2,3,1,"","value_as_byte_buf"],[2,3,1,"","value_as_int16"],[2,3,1,"","value_as_int32"],[2,3,1,"","value_as_int64"],[2,3,1,"","value_as_string"],[2,3,1,"","value_as_timestamp"],[2,3,1,"","value_as_uuid"]],"awscrt.eventstream.HeaderType":[[2,2,1,"","BOOL_FALSE"],[2,2,1,"","BOOL_TRUE"],[2,2,1,"","BYTE"],[2,2,1,"","BYTE_BUF"],[2,2,1,"","INT16"],[2,2,1,"","INT32"],[2,2,1,"","INT64"],[2,2,1,"","STRING"],[2,2,1,"","TIMESTAMP"],[2,2,1,"","UUID"]],"awscrt.eventstream.rpc":[[2,1,1,"","ClientConnection"],[2,1,1,"","ClientConnectionHandler"],[2,1,1,"","ClientContinuation"],[2,1,1,"","ClientContinuationHandler"],[2,1,1,"","MessageFlag"],[2,1,1,"","MessageType"]],"awscrt.eventstream.rpc.ClientConnection":[[2,3,1,"","close"],[2,3,1,"","connect"],[2,2,1,"","host_name"],[2,3,1,"","is_open"],[2,3,1,"","new_stream"],[2,2,1,"","port"],[2,3,1,"","send_protocol_message"],[2,2,1,"","shutdown_future"]],"awscrt.eventstream.rpc.ClientConnectionHandler":[[2,3,1,"","on_connection_setup"],[2,3,1,"","on_connection_shutdown"],[2,3,1,"","on_protocol_message"]],"awscrt.eventstream.rpc.ClientContinuation":[[2,3,1,"","activate"],[2,2,1,"","closed_future"],[2,2,1,"","connection"],[2,3,1,"","send_message"]],"awscrt.eventstream.rpc.ClientContinuationHandler":[[2,3,1,"","on_continuation_closed"],[2,3,1,"","on_continuation_message"]],"awscrt.eventstream.rpc.MessageFlag":[[2,2,1,"","CONNECTION_ACCEPTED"],[2,2,1,"","NONE"],[2,2,1,"","TERMINATE_STREAM"]],"awscrt.eventstream.rpc.MessageType":[[2,2,1,"","APPLICATION_ERROR"],[2,2,1,"","APPLICATION_MESSAGE"],[2,2,1,"","CONNECT"],[2,2,1,"","CONNECT_ACK"],[2,2,1,"","INTERNAL_ERROR"],[2,2,1,"","PING"],[2,2,1,"","PING_RESPONSE"],[2,2,1,"","PROTOCOL_ERROR"]],"awscrt.exceptions":[[3,6,1,"","AwsCrtError"],[3,5,1,"","from_code"]],"awscrt.exceptions.AwsCrtError":[[3,2,1,"","code"],[3,2,1,"","message"],[3,2,1,"","name"]],"awscrt.http":[[4,1,1,"","HttpClientConnection"],[4,1,1,"","HttpClientStream"],[4,1,1,"","HttpHeaders"],[4,1,1,"","HttpProxyAuthenticationType"],[4,1,1,"","HttpProxyConnectionType"],[4,1,1,"","HttpProxyOptions"],[4,1,1,"","HttpRequest"],[4,1,1,"","HttpVersion"]],"awscrt.http.HttpClientConnection":[[4,3,1,"","close"],[4,4,1,"","host_name"],[4,3,1,"","is_open"],[4,3,1,"","new"],[4,4,1,"","port"],[4,3,1,"","request"],[4,4,1,"","shutdown_future"],[4,4,1,"","version"]],"awscrt.http.HttpClientStream":[[4,3,1,"","activate"],[4,2,1,"","completion_future"],[4,2,1,"","connection"],[4,4,1,"","response_status_code"]],"awscrt.http.HttpHeaders":[[4,3,1,"","add"],[4,3,1,"","add_pairs"],[4,3,1,"","clear"],[4,3,1,"","get"],[4,3,1,"","get_values"],[4,3,1,"","remove"],[4,3,1,"","remove_value"],[4,3,1,"","set"]],"awscrt.http.HttpProxyAuthenticationType":[[4,2,1,"","Basic"],[4,2,1,"","Nothing"]],"awscrt.http.HttpProxyConnectionType":[[4,2,1,"","Forwarding"],[4,2,1,"","Legacy"],[4,2,1,"","Tunneling"]],"awscrt.http.HttpProxyOptions":[[4,2,1,"","auth_password"],[4,2,1,"","auth_type"],[4,2,1,"","auth_username"],[4,2,1,"","connection_type"],[4,2,1,"","host_name"],[4,2,1,"","port"],[4,2,1,"","tls_connection_options"]],"awscrt.http.HttpRequest":[[4,4,1,"","body_stream"],[4,4,1,"","headers"],[4,4,1,"","method"],[4,4,1,"","path"]],"awscrt.http.HttpVersion":[[4,2,1,"","Http1_0"],[4,2,1,"","Http1_1"],[4,2,1,"","Http2"],[4,2,1,"","Unknown"]],"awscrt.io":[[5,1,1,"","ClientBootstrap"],[5,1,1,"","ClientTlsContext"],[5,1,1,"","DefaultHostResolver"],[5,1,1,"","EventLoopGroup"],[5,1,1,"","HostResolverBase"],[5,1,1,"","InputStream"],[5,1,1,"","LogLevel"],[5,1,1,"","Pkcs11Lib"],[5,1,1,"","SocketDomain"],[5,1,1,"","SocketOptions"],[5,1,1,"","SocketType"],[5,1,1,"","TlsConnectionOptions"],[5,1,1,"","TlsContextOptions"],[5,1,1,"","TlsVersion"],[5,5,1,"","init_logging"],[5,5,1,"","is_alpn_available"]],"awscrt.io.ClientBootstrap":[[5,2,1,"","shutdown_event"]],"awscrt.io.ClientTlsContext":[[5,3,1,"","new_connection_options"]],"awscrt.io.EventLoopGroup":[[5,2,1,"","shutdown_event"]],"awscrt.io.InputStream":[[5,3,1,"","wrap"]],"awscrt.io.LogLevel":[[5,2,1,"","Debug"],[5,2,1,"","Error"],[5,2,1,"","Fatal"],[5,2,1,"","Info"],[5,2,1,"","NoLogs"],[5,2,1,"","Trace"],[5,2,1,"","Warn"]],"awscrt.io.Pkcs11Lib":[[5,1,1,"","InitializeFinalizeBehavior"]],"awscrt.io.Pkcs11Lib.InitializeFinalizeBehavior":[[5,2,1,"","DEFAULT"],[5,2,1,"","OMIT"],[5,2,1,"","STRICT"]],"awscrt.io.SocketDomain":[[5,2,1,"","IPv4"],[5,2,1,"","IPv6"],[5,2,1,"","Local"]],"awscrt.io.SocketOptions":[[5,2,1,"","connect_timeout_ms"],[5,2,1,"","domain"],[5,2,1,"","keep_alive"],[5,2,1,"","keep_alive_interval_secs"],[5,2,1,"","keep_alive_max_probes"],[5,2,1,"","keep_alive_timeout_secs"],[5,2,1,"","type"]],"awscrt.io.SocketType":[[5,2,1,"","DGram"],[5,2,1,"","Stream"]],"awscrt.io.TlsConnectionOptions":[[5,3,1,"","set_alpn_list"],[5,3,1,"","set_server_name"],[5,2,1,"","tls_ctx"]],"awscrt.io.TlsContextOptions":[[5,2,1,"","alpn_list"],[5,3,1,"","create_client_with_mtls"],[5,3,1,"","create_client_with_mtls_from_path"],[5,3,1,"","create_client_with_mtls_pkcs11"],[5,3,1,"","create_client_with_mtls_pkcs12"],[5,3,1,"","create_client_with_mtls_windows_cert_store_path"],[5,3,1,"","create_server"],[5,3,1,"","create_server_from_path"],[5,3,1,"","create_server_pkcs12"],[5,2,1,"","min_tls_ver"],[5,3,1,"","override_default_trust_store"],[5,3,1,"","override_default_trust_store_from_path"],[5,2,1,"","verify_peer"]],"awscrt.io.TlsVersion":[[5,2,1,"","DEFAULT"],[5,2,1,"","SSLv3"],[5,2,1,"","TLSv1"],[5,2,1,"","TLSv1_1"],[5,2,1,"","TLSv1_2"],[5,2,1,"","TLSv1_3"]],"awscrt.mqtt":[[6,1,1,"","Client"],[6,1,1,"","ConnectReturnCode"],[6,1,1,"","Connection"],[6,1,1,"","QoS"],[6,6,1,"","SubscribeError"],[6,1,1,"","WebsocketHandshakeTransformArgs"],[6,1,1,"","Will"]],"awscrt.mqtt.ConnectReturnCode":[[6,2,1,"","ACCEPTED"],[6,2,1,"","BAD_USERNAME_OR_PASSWORD"],[6,2,1,"","IDENTIFIER_REJECTED"],[6,2,1,"","NOT_AUTHORIZED"],[6,2,1,"","SERVER_UNAVAILABLE"],[6,2,1,"","UNACCEPTABLE_PROTOCOL_VERSION"]],"awscrt.mqtt.Connection":[[6,3,1,"","connect"],[6,3,1,"","disconnect"],[6,3,1,"","on_message"],[6,3,1,"","publish"],[6,3,1,"","resubscribe_existing_topics"],[6,3,1,"","subscribe"],[6,3,1,"","unsubscribe"]],"awscrt.mqtt.QoS":[[6,2,1,"","AT_LEAST_ONCE"],[6,2,1,"","AT_MOST_ONCE"],[6,2,1,"","EXACTLY_ONCE"]],"awscrt.mqtt.WebsocketHandshakeTransformArgs":[[6,2,1,"","http_request"],[6,2,1,"","mqtt_connection"],[6,3,1,"","set_done"]],"awscrt.mqtt.Will":[[6,2,1,"","payload"],[6,2,1,"","qos"],[6,2,1,"","retain"],[6,2,1,"","topic"]],"awscrt.s3":[[7,1,1,"","S3Client"],[7,1,1,"","S3Request"],[7,1,1,"","S3RequestTlsMode"],[7,1,1,"","S3RequestType"]],"awscrt.s3.S3Client":[[7,3,1,"","make_request"]],"awscrt.s3.S3Request":[[7,2,1,"","finished_future"],[7,2,1,"","shutdown_event"]],"awscrt.s3.S3RequestTlsMode":[[7,2,1,"","DISABLED"],[7,2,1,"","ENABLED"]],"awscrt.s3.S3RequestType":[[7,2,1,"","DEFAULT"],[7,2,1,"","GET_OBJECT"],[7,2,1,"","PUT_OBJECT"]],awscrt:[[0,0,0,"-","auth"],[1,0,0,"-","common"],[2,0,0,"-","eventstream"],[3,0,0,"-","exceptions"],[4,0,0,"-","http"],[5,0,0,"-","io"],[6,0,0,"-","mqtt"],[7,0,0,"-","s3"]]},objnames:{"0":["py","module","Python module"],"1":["py","class","Python class"],"2":["py","attribute","Python attribute"],"3":["py","method","Python method"],"4":["py","property","Python property"],"5":["py","function","Python function"],"6":["py","exception","Python exception"]},objtypes:{"0":"py:module","1":"py:class","2":"py:attribute","3":"py:method","4":"py:property","5":"py:function","6":"py:exception"},terms:{"0":[0,2,4,5,6,7],"05":0,"1":[0,2,3,4,5,6,7],"1024":7,"11":5,"12":5,"1200":6,"128":5,"16":[2,5],"2":[2,4,5,6,7],"2019":0,"2020":6,"21":0,"256":0,"29t00":0,"3":[2,4,5,6],"3000":6,"32":2,"4":[0,2,5,6],"43z":0,"5":[2,5,6,7],"509":5,"5mb":7,"5x":6,"6":[2,5],"60":6,"64":2,"7":[2,5],"8":[2,6],"9":2,"abstract":2,"byte":[2,5,6,7],"case":[4,5],"class":[0,2,3,4,5,6,7],"default":[0,2,4,5,6,7],"do":[0,5,6],"final":6,"float":7,"function":[0,2,4,6,7],"import":5,"int":[0,1,2,3,4,5,6,7],"long":5,"new":[0,2,4,6,7],"public":0,"return":[0,1,2,3,4,5,6,7],"static":[0,5],"true":[0,2,4,5,6],"try":7,"while":[5,6,7],A:[0,2,4,5,6],At:6,By:0,For:[2,3,5,6],If:[0,2,4,5,6,7],In:[0,4],It:[0,6],No:[2,4,6,7],Not:2,On:0,The:[0,2,4,5,6,7],There:6,To:[0,5],Will:6,_base:2,a11f8a9b5df5b98ba3508fbca575d09570e0d2c6:5,abc:[0,2],about:3,absent:2,acceler:7,accept:[0,2,6],access:[0,1,5],access_key_id:0,accesskei:0,accesskeyid:0,accommod:5,accord:[0,6],acknowledg:[2,5,6],across:6,activ:[2,4],actual:[2,6],ad:0,add:[0,4],add_pair:4,addit:4,after:[2,6],again:[5,6],against:0,agent:0,aka:3,algorithm:0,aliv:[2,6],all:[0,2,4,5,6,7],allow:[5,6],allow_non:5,alpn:5,alpn_list:5,alreadi:[0,2,4,5,6],also:[0,5],alwai:[0,2,4],amazon:0,amount:6,amz:0,amzn:0,an:[0,2,3,4,5,6,7],ani:[2,4,5,6],anoth:[5,6],api:7,appl:5,appli:[0,6],applic:[2,5,6],application_error:2,application_messag:2,appropri:3,ar:[0,2,4,5,6,7],argsa:0,argument:[0,2,4,5,6,7],armor:5,arriv:[2,4,6],ask:5,associ:[0,6],assum:[0,5,6],asymmetr:0,async:[5,6],asynchron:[0,2,4,5,6],at_least_onc:6,at_most_onc:6,attempt:[2,4,6],attribut:0,auth:8,auth_password:4,auth_typ:4,auth_usernam:4,authent:[0,4,5,7],author:[0,6],automat:6,avail:[2,5],avoid:2,aw:[0,3,6,7,8],aws4:0,aws_access_key_id:0,aws_config_fil:0,aws_error_oom:3,aws_profil:0,aws_secret_access_kei:0,aws_session_token:0,aws_shared_credentials_fil:0,aws_sign_request:0,awscredenti:[0,7],awscredentialsprovid:[0,7],awscrterror:[3,6],awslab:8,awssignaturetyp:0,awssignedbodyheadertyp:0,awssignedbodyvalu:0,awssigningalgorithm:0,awssigningconfig:0,backslash:5,bad:6,bad_username_or_password:6,base:[0,2,3,5],baseexcept:3,basic:4,becaus:[2,7],been:[0,2,4,6,7],befor:[0,4,5,6,7],begin:[4,5,7],behavior:5,being:[0,5,6],better:7,between:[5,6],bin:0,binari:[2,4,5],bind:[0,8],bit:2,bodi:[0,4,7],body_stream:[4,7],bool:[0,2,4,5,6],bool_fals:2,bool_tru:2,bootstrap:[0,2,4,6,7],both:[0,5],bucket:7,buffer:[4,5,6,7],build:0,built:0,byte_buf:2,bytestr:2,c_final:5,c_initi:5,ca:5,ca_dirpath:5,ca_filepath:5,cach:5,calcul:0,call:[2,4,5,6],callabl:[0,2],callback:[0,2,4,6,7],can:[0,2,4,5,6,7],cancel:6,cannot:6,canon:0,cap:5,capabl:6,carri:4,caus:[4,6],cert_buff:5,cert_file_cont:5,cert_file_path:5,cert_filepath:5,cert_path:5,certain:0,certif:5,chain:[0,5],chang:2,cheap:5,check:[0,2,4,5],chosen:5,chunk:[0,4,7],classmethod:[0,2,4,5],clean:6,clean_sess:6,cleanup:5,clear:4,client:[0,2,4,5,6,7],client_bootstrap:0,client_id:6,clientbootstrap:[0,2,4,5,6,7],clientconnect:2,clientconnectionhandl:2,clientcontinu:2,clientcontinuationhandl:2,clienttlscontext:[5,6],close:[2,4,6],closed_futur:2,code:[3,4,5,6,7],collect:[2,4,5],com:8,command:0,common:[2,3,5,8],compat:[2,4,5,6,7],complet:[0,2,4,6],completion_futur:4,comput:0,concurr:[0,2,4,5,6,7],condit:[0,5],config:0,config_filepath:0,configur:[0,5],connect:[0,2,4,5,6,7],connect_ack:2,connect_timeout_m:5,connection_accept:2,connection_typ:4,connectionless:5,connectreturncod:6,consid:5,construct:[0,4],consult:2,contain:[0,2,4,5,6,7],content:[0,5,6],context:[5,6],continu:2,continuation_handl:2,control:[0,5],convert:0,core:6,correct:6,cpu_group:5,creat:[0,2,4,5,7],create_client_with_mtl:5,create_client_with_mtls_from_path:5,create_client_with_mtls_pkcs11:5,create_client_with_mtls_pkcs12:5,create_client_with_mtls_windows_cert_store_path:5,create_serv:5,create_server_from_path:5,create_server_pkcs12:5,create_x:5,creation:5,credenti:[0,6,7],credential_process:0,credential_provid:7,credentials_filepath:0,credentials_provid:0,criteria:5,cross:1,crt:8,current:6,currentus:5,currentusermya11f8a9b5df5b98ba3508fbca575d09570e0d2c6:[],custom:[0,5],data:[0,2,4,6,7],datagram:5,date:0,datetim:0,debug:5,defaulthostresolv:5,defin:0,definit:4,deliv:[2,6],deliveri:6,deprec:6,deriv:0,desir:6,destin:5,destroi:[5,7],detect:5,determin:[2,6],devic:[5,6],dgram:5,dict:[2,4,6,7],differ:[0,2],directli:7,directori:5,disabl:[5,6,7],disconnect:[5,6],disk:5,displai:5,distinct:4,dn:5,document:2,doe:[0,4,6],domain:5,done:[2,6,7],done_futur:6,doubl:[0,6],down:[0,2,4,5,7],download:7,dup:6,duplic:6,durat:[5,6],dure:0,e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855:0,e:0,each:[0,2,5,6,7],earlier:6,ec2:0,ec:0,ecc:0,effect:[0,2,4],either:6,els:7,empti:[0,4,6],empty_sha256:0,enabl:7,encod:[0,4,7],end:[2,4,5],endpoint:4,ensur:6,enumer:[0,2,4,5,6],environ:0,epoch:2,equal:0,error:[2,3,4,5,6,7],error_bodi:7,error_head:7,establish:[2,4,6],even:[2,7],event:[0,2,4,5,7],event_loop_group:5,eventloopgroup:5,eventstream:8,eventu:4,ex:[4,5],exactli:6,exactly_onc:6,exampl:[0,2,3,5,6],except:[0,2,4,5,6,7,8],exchang:4,exist:[4,6],expect:2,expens:5,expir:0,expiration_in_second:0,extern:0,fail:[0,2,4,5,6,7],failur:6,fals:[0,2,4,5,6],fatal:5,fetch:[0,6],fetcher:0,file:[0,5,7],file_nam:5,filter:6,finish:[2,4,5,7],finished_futur:7,fire:[2,4],first:[0,2,4],fit:2,fix:0,flag:[2,6],fn:6,follow:[0,2,4,6,7],forget:6,forgotten:6,format:[0,5],forward:[2,4,6,7],found:4,from:[0,2,4,5,6,7],from_bool:2,from_byt:2,from_byte_buf:2,from_cod:3,from_int16:2,from_int32:2,from_int64:2,from_str:2,from_timestamp:2,from_uuid:2,from_x:2,full:0,further:2,futur:[0,2,4,6,7],g:0,garbag:4,gbp:7,gener:0,get:[0,4,7],get_cpu_count_for_group:1,get_cpu_group_count:1,get_credenti:0,get_object:7,get_valu:4,github:8,give:7,given:[0,1,2,3,4,5],good:0,grant:6,greater:7,group:[1,5],group_idx:1,ha:[0,2,4,5,6,7],handl:[2,5],handler:2,handshak:6,hang:6,happen:7,hasn:2,have:[4,5,7],header:[0,2,4,6,7],header_typ:2,headertyp:2,help:6,here:[0,7],hex:0,higher:[5,6],highest:6,hmac:0,hood:7,host:[2,4,5],host_nam:[2,4,6],host_resolv:5,hostnam:4,hostresolverbas:5,how:[5,7],http1_0:4,http1_1:4,http2:4,http:[0,6,8],http_request:[0,6],http_request_head:0,http_request_query_param:0,http_stream:4,httpclientconnect:4,httpclientstream:4,httpheader:4,httpproxyauthenticationtyp:4,httpproxyconnectiontyp:4,httpproxyopt:[4,6],httprequest:[0,4,6,7],httpversion:4,i:5,id:[0,2,5,6],identifi:[0,6],identifier_reject:6,idl:5,ignor:[4,5,7],immut:0,implement:6,includ:6,increas:6,index:8,indic:[2,4,5,6,7],info:[0,5,6],inform:[2,6],inherit:2,init_log:5,initi:[0,2,4,5,6,7],initializefinalizebehavior:5,inject:0,inputstream:[4,5],insensit:4,instanc:[0,5],instead:[0,5,6,7],int16:2,int32:2,int64:2,intern:[0,2,5],internal_error:2,interv:6,invalid:6,invok:[2,4,6,7],io:[2,4,6,8],iobas:[4,5],iot:6,ipv4:5,ipv6:5,is_alpn_avail:5,is_open:[2,4],iter:4,its:[2,4,6],job:7,json:0,just:[0,5,7],keep:6,keep_al:5,keep_alive_interval_sec:5,keep_alive_max_prob:5,keep_alive_sec:6,keep_alive_timeout_sec:5,keepal:5,kei:[0,5],key_buff:5,keyerror:4,keyword:[0,2,5,7],know:[2,4],kwarg:[0,2,4,6,7],label:5,lack:0,layer:5,leak:[2,5],least:[5,6],legaci:4,level:6,librari:[1,2,5],lifetim:5,like:[2,5],list:[0,4,5,6,7],live:7,load:[0,5],local:[0,2,4,5],log:5,log_level:5,logic:4,loglevel:5,longer:[0,6],look:0,loop:[2,4,5],loss:6,lost:[5,6],lower:6,lowercas:0,machin:5,made:[2,6],mai:[0,2,4,5,6],main:4,make:[4,5,7],make_request:7,malform:6,mani:5,manner:4,mark:6,match:6,max:[5,6],max_host:5,maximum:[5,6],mean:5,member:6,memori:[1,5],memoryerror:3,mesag:6,messag:[2,3,5,6],message_typ:2,messageflag:2,messagetyp:2,metadata:0,method:[2,4,5],might:[0,6],millisecond:[5,6],min:6,min_tls_ver:5,minimum:[5,6],mode:[5,7],modifi:6,more:[2,6],most:[0,5,6],mqtt:8,mqtt_connect:6,multi:7,multipl:[4,7],must:[2,4,5,6],mutual:5,my:[0,5],naiv:0,name:[0,2,3,4,5,6,7],name_value_pair:4,nativ:5,nearest:0,necessarili:[4,7],need:[0,5,7],negoti:5,neither:6,network:[2,4,5,6],never:[2,5],new_chain:0,new_connection_opt:5,new_default_chain:0,new_deleg:0,new_environ:0,new_process:0,new_profil:0,new_stat:0,new_stream:2,new_x:0,node:[1,5],nolog:5,non:[1,5],none:[0,2,4,5,6,7],nor:6,normal:0,not_author:6,note:[2,4,5,6,7],noth:[2,4,6,7],now:[0,6],num_thread:5,numa:[1,5],number:[1,4,5,7],o:5,object:[0,2,5,7],occur:[2,4],off:0,offlin:6,offset:7,old:[0,4],omit:[0,5],omit_session_token:0,on_bodi:[4,7],on_connection_interrupt:6,on_connection_resum:6,on_connection_setup:2,on_connection_shutdown:2,on_continuation_clos:2,on_continuation_messag:2,on_don:7,on_flush:2,on_head:7,on_messag:6,on_progress:7,on_protocol_messag:2,on_respons:4,onc:[2,4,6,7],one:[0,2,5,7],onli:[0,2,5,7],open:[2,4,6],oper:[0,2,4,5,6,7],opt:0,option:[0,2,4,5,6,7],order:0,org:8,other:[2,5,6,7],otherwis:[0,2,3,4,5,6],out:4,outgo:[4,5,7],output:0,over:[2,4,5,6],overal:7,overhead:6,overrid:[0,2,5],override_default_trust_stor:5,override_default_trust_store_from_path:5,packet:6,packet_id:6,page:8,pair:[4,7],param:0,paramet:[0,2,3,4,5,6],part:[0,5,7],part_siz:7,particular:0,pass:[0,5,6,7],password:[4,5,6],past:0,path:[0,4,5,6,7],pattern:2,payload:[0,2,6],peer:5,pem:5,per:5,perfect:5,perform:[0,6,7],period:5,pin:5,ping:[2,6],ping_respons:2,ping_timeout_m:6,pk_filepath:5,pkc:5,pkcs11_lib:5,pkcs11lib:5,pkcs12_filepath:5,pkcs12_password:5,place:6,plain:[2,4],platform:1,plu:6,port:[2,4,6],posix:2,possibl:6,practic:0,precalcul:0,preced:0,present:[2,6],previou:[5,6],privat:[0,5],private_key_label:5,probe:5,procedur:2,process:[0,2],processor:[1,5],profil:0,profile_nam:0,profile_to_us:0,progress:7,project:8,properti:[0,2,4],protect:5,protocol:[2,4,5,6],protocol_error:2,protocol_operation_timeout_m:6,provid:[0,2,4,5,6,7],proxi:[4,6],proxy_opt:[4,6],puback:6,pubcomp:6,publish:6,put:7,put_object:7,pypi:8,python:[3,5,8],qo:6,qos1:6,qualiti:6,queri:[0,2,4],r:[],rais:[2,4,5],rather:0,raw:2,re:[2,4,6],reach:[6,7],read:[0,5,7],readi:[2,4],reason:2,receiv:[2,4,5,6,7],reconnect:6,reconnect_max_timeout_sec:6,reconnect_min_timeout_sec:6,recv_filepath:7,refer:2,refus:6,regardless:7,region:[0,7],reject:[2,6],relat:0,relax:5,reliabl:5,remain:2,rememb:6,remot:[2,4],remov:4,remove_valu:4,replac:0,report:[5,7],request:[0,4,6,7],requir:[0,6,7],resolv:[5,7],resourc:[0,2,5],respond:6,respons:[2,4,6,7],response_status_cod:4,resubscrib:6,resubscribe_existing_top:6,result:[0,2,3,4,6],resum:6,retain:6,retransmiss:5,retri:6,return_cod:6,rootca_buff:5,round:0,rpc:2,rule:0,run:[0,5],runtim:[3,8],s3:[0,8],s3client:7,s3request:7,s3requesttlsmod:7,s3requesttyp:7,s:[0,2,3,4,5,7],same:[0,2,5],scope:6,sdk:0,search:8,sec:6,second:[0,2,5,6],secret:0,secret_access_kei:0,secretaccesskei:0,secur:[0,6],see:[0,5,6],select:0,send:[2,4,5,6],send_filepath:7,send_messag:2,send_protocol_messag:2,sender:[2,6],sent:[2,4,6,7],sequenc:[0,2],server:[4,5,6,7],server_nam:5,server_unavail:6,servic:[0,6],session:[0,6],session_pres:6,session_token:0,sessiontoken:0,set:[0,4,5,6,7],set_alpn_list:5,set_don:6,set_server_nam:5,setup:[2,5],sever:0,sha256:0,sha:0,share:5,shorter:6,should:[0,2,4,5,6,7],should_normalize_uri_path:0,should_sign_head:0,shut:[2,4,5,7],shutdown:[2,4,5,7],shutdown_ev:[5,7],shutdown_futur:[2,4],side:[0,7],sign:[0,2,4,6,7],signabl:0,signal:[5,7],signatur:[0,6],signature_typ:0,signed_body_header_typ:0,signed_body_valu:0,signedhead:0,signer:0,signing_config:0,simpl:0,simpli:[2,7],sinc:2,singl:5,singleton:[2,4,6,7],size:7,skip:[0,5],skippabl:0,slot:5,slot_id:5,sni:5,so:6,socket:[0,2,4,5,6,7],socket_opt:[2,4,6],socketdomain:5,socketopt:[2,4,5,6],sockettyp:5,some:[0,5],someth:[5,6],soon:6,sort:0,sourc:[0,7],spawn:6,special:0,specif:[2,4,5],specifi:[0,4,5],split:7,sslv3:5,stai:2,standard:0,start:[6,7],state:2,statu:[4,7],status_cod:[4,7],stderr:5,stdout:5,still:5,store:[2,5,6],str:[0,2,3,4,5,6,7],stream:[0,2,4,5,7],streaming_aws4_hmac_sha256_ev:0,streaming_aws4_hmac_sha256_payload:0,strict:5,string:[0,2,5],structur:7,suback:6,subscrib:6,subscribeerror:6,subscript:6,succe:[2,4,6],success:[2,4,6],successfulli:[0,2,6,7],supplement:0,support:[2,5,6],synchron:0,system:[1,5],t:2,take:[0,2,4,6,7],target:7,tcp:5,termin:2,terminate_stream:2,text:[2,4],than:[6,7],thei:[0,2,5,6],them:[2,5],thi:[0,2,4,5,6,7],those:[0,7],though:6,thread:[0,2,4,5,7],through:4,throughput:7,throughput_target_gbp:7,thumbprint:5,time:[0,4,6,7],timeout:[5,6],timestamp:2,timezon:0,tl:[2,4,5,6,7],tls_connection_opt:[2,4,7],tls_ctx:[5,6],tls_mode:7,tlsconnectionopt:[2,4,5,7],tlscontextopt:5,tlsv1:5,tlsv1_1:5,tlsv1_2:5,tlsv1_3:5,tlsversion:5,togeth:2,token:[0,5],token_label:5,too:0,topic:6,trace:[0,5],transfer:7,transform:[0,4,6],transform_arg:6,transmiss:5,transmit:[2,5],treat:[4,5],trust:5,tunnel:4,tupl:[4,6,7],two:5,type:[0,2,3,4,5,6,7],typic:0,udp:5,ultim:4,unaccept:6,unacceptable_protocol_vers:6,unavail:6,under:7,underli:[6,7],unencrypt:6,unexpectedli:6,uniform:[1,5],union:[4,5],uniqu:6,unix:[2,5],unknown:4,unless:7,unreli:5,unset:7,unsign:0,unsigned_payload:0,unspecifi:5,unsuback:6,unsubscrib:6,unsuccess:[6,7],until:[0,2,4,6],unus:0,updat:0,upload:7,upon:2,us:[0,1,2,4,5,6,7],usabl:[2,4],use_double_uri_encod:0,use_websocket:6,user:[0,2,5,6],user_pin:5,usernam:[4,6],usual:0,utc:0,utf:[2,6],uuid:2,v4:0,v4_asymmetr:0,valgrind:5,valid:[0,4,5,7],valu:[0,2,3,4,5,6,7],value_as_bool:2,value_as_byt:2,value_as_byte_buf:2,value_as_int16:2,value_as_int32:2,value_as_int64:2,value_as_str:2,value_as_timestamp:2,value_as_uuid:2,value_as_x:2,valueerror:4,variabl:0,verb:4,verify_p:5,version:[0,4,5,6],via:[2,5,6],wa:[2,6,7],wai:[0,5],wait:6,want:5,warn:5,we:7,websocket:6,websocket_handshake_transform:6,websocket_proxy_opt:6,websockethandshaketransformarg:6,went:6,were:6,what:0,when:[0,2,4,5,6,7],whenev:6,where:6,whether:[0,5,6],which:[0,2,4,5,6],whichev:0,whole:[4,7],whose:[0,6],why:[2,4,7],wildcard:6,window:5,wire:2,wish:5,within:[2,6],without:6,work:[1,5,6],would:[4,6],wrap:5,write:[2,5,6,7],written:[0,2,6,7],wrong:6,x:[0,5],x_amz_content_sha_256:0,xore:2,you:[2,4,5],your:5,zero:6},titles:["awscrt.auth","awscrt.common","awscrt.eventstream","awscrt.exceptions","awscrt.http","awscrt.io","awscrt.mqtt","awscrt.s3","Welcome to awscrt\u2019s documentation!"],titleterms:{api:8,auth:0,awscrt:[0,1,2,3,4,5,6,7,8],common:1,document:8,eventstream:2,except:3,http:4,indic:8,io:5,mqtt:6,refer:8,s3:7,s:8,tabl:8,welcom:8}})