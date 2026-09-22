<?php
// Isolated WordPress function doubles: no live site or database writes.
define('ABSPATH', __DIR__);
class WP_Error { public $code; function __construct($code,$message,$data) { $this->code=$code; } }
function add_action($a,$b) {}
function get_post_type($id) { return 'attachment'; }
function wp_attachment_is_image($id) { return true; }
function sanitize_file_name($name) { return str_replace('.fr.', '.fr_.', $name); }
function wp_upload_dir() { return array('basedir'=>$GLOBALS['base']); }
function get_attached_file($id,$unfiltered=false) { return $GLOBALS['base'].'/'.$GLOBALS['attached']; }
function get_post_meta($id,$key,$single) { return $key==='_wp_attached_file' ? $GLOBALS['attached'] : ($GLOBALS['extra'][$key]??''); }
function wp_get_attachment_metadata($id) { return $GLOBALS['meta']; }
function wp_get_attachment_url($id) { return 'https://example.test/uploads/'.$GLOBALS['attached']; }
function update_post_meta($id,$key,$value) { if($key==='_wp_attached_file'){$GLOBALS['attached']=$value;}else{$GLOBALS['extra'][$key]=$value;} return true; }
function update_attached_file($id,$path) { $GLOBALS['attached']=substr($path,strlen($GLOBALS['base'])+1); }
function wp_update_attachment_metadata($id,$data) { if(empty($GLOBALS['fail_meta'])){$GLOBALS['meta']=$data;} }
function clean_post_cache($id) {}
require __DIR__.'/../../wordpress/zpsi-media/zpsi-media.php';
function verify($value,$message) { if(!$value){throw new Exception($message);} }
$base=sys_get_temp_dir().'/zpsi-rename-'.bin2hex(random_bytes(6));mkdir($base);
try {
    $old='sac-01__123456789abc.webp';$new='sac-01__123456789abc-www.example.fr.webp';
    $attached=$old;
    $meta=array('file'=>$old,'sizes'=>array('thumbnail'=>array('file'=>'sac-01__123456789abc-150x150.webp')));
    file_put_contents($base.'/'.$old,'image');file_put_contents($base.'/'.$meta['sizes']['thumbnail']['file'],'thumb');
    $request=array('id'=>7,'filename'=>$new,'expected_url'=>wp_get_attachment_url(7));
    $result=zpsi_media_rename($request);
    verify(is_array($result)&&$result['id']===7,'same attachment ID');
    verify($attached===sanitize_file_name($new),'new attached path');
    verify(is_file($base.'/'.$old),'old URL retained');
    verify(is_file($base.'/'.$meta['sizes']['thumbnail']['file']),'new thumbnail exists');
    verify(zpsi_media_rename($request)['renamed']===false,'idempotent after lost response');
    $bad=$request;$bad['filename']='../escape.webp';verify(zpsi_media_rename($bad) instanceof WP_Error,'path traversal blocked');
    $bad=$request;$bad['filename']='other-01__aaaaaaaaaaaa.webp';verify(zpsi_media_rename($bad) instanceof WP_Error,'identity mismatch blocked');
    $before=$attached;
    $bad=$request;$bad['filename']='sac-01__123456789abc-www.other.fr.webp';$bad['expected_url']=wp_get_attachment_url(7);
    file_put_contents($base.'/'.sanitize_file_name($bad['filename']),'collision');
    verify(zpsi_media_rename($bad) instanceof WP_Error,'collision blocked');verify($attached===$before,'path unchanged on collision');
    unlink($base.'/'.sanitize_file_name($bad['filename']));
    $fail_meta=true;
    verify(zpsi_media_rename($bad) instanceof WP_Error,'metadata write failure reported');
    verify($attached===$before,'attachment restored after failure');
    verify(!file_exists($base.'/'.sanitize_file_name($bad['filename'])),'new file rolled back');
    echo "PASS: same ID, old URLs, thumbnails, idempotency, traversal, identity, collision, rollback\n";
} finally {
    foreach(glob($base.'/*') as $file){unlink($file);}unlink($base.'/.zpsi-media.lock');rmdir($base);
}
