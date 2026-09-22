<?php
/**
 * Plugin Name: ZPSI Media
 * Description: Renomme les images ZPSI en conservant leur identifiant et les anciennes adresses.
 * Version: 0.1.0
 * Requires PHP: 7.4
 */
if (!defined('ABSPATH')) { exit; }

function zpsi_media_identity($name) {
    $name = preg_replace('/\.([a-zA-Z]{2,5}[0-9]?)_\./', '.$1.', $name);
    if (preg_match('/^(.+-[0-9]+__[a-f0-9]{12})(?:-www\.[a-z0-9.-]+)?\.(webp|jpg|jpeg|png)$/D', $name, $m)) {
        return $m[1] . '.' . $m[2];
    }
    return false;
}

function zpsi_media_rename($request) {
    $id = (int) $request['id'];
    $requested = (string) $request['filename'];
    if (get_post_type($id) !== 'attachment' || !wp_attachment_is_image($id)) {
        return new WP_Error('zpsi_not_image', 'Média image introuvable.', array('status' => 404));
    }
    if (strlen($requested) > 240 || basename($requested) !== $requested || !preg_match('/^[a-zA-Z0-9_.-]+\.(webp|jpg|jpeg|png)$/D', $requested)) {
        return new WP_Error('zpsi_invalid_name', 'Nom de fichier invalide.', array('status' => 400));
    }
    $target_name = sanitize_file_name($requested);
    $uploads = wp_upload_dir();
    $base = realpath($uploads['basedir']);
    $file = get_attached_file($id, true);
    $source = realpath($file);
    if (!$base || !$source || strpos($source, $base . DIRECTORY_SEPARATOR) !== 0 || is_link($file)) {
        return new WP_Error('zpsi_external', 'Seuls les fichiers locaux du dossier uploads sont pris en charge.', array('status' => 409));
    }
    // One lock for all renames prevents collisions between two attachment IDs.
    $lock = fopen($base . '/.zpsi-media.lock', 'c');
    if (!$lock || !flock($lock, LOCK_EX | LOCK_NB)) {
        if ($lock) { fclose($lock); }
        return new WP_Error('zpsi_busy', 'Un renommage est déjà en cours.', array('status' => 409));
    }
    $old_meta = wp_get_attachment_metadata($id);
    $old_attached = get_post_meta($id, '_wp_attached_file', true);
    $created = array();
    $changed = false;
    try {
        $old_name = basename($source);
        if ($old_name === $target_name) {
            if (!is_array($old_meta) || basename($old_meta['file'] ?? '') !== $target_name) {
                throw new RuntimeException('Renommage incomplet : vérifier les métadonnées avant de reprendre.');
            }
            return array('id' => $id, 'url' => wp_get_attachment_url($id), 'filename' => $target_name, 'renamed' => false);
        }
        $identity = zpsi_media_identity($old_name);
        if (!$identity || $identity !== zpsi_media_identity($target_name)) {
            throw new RuntimeException('Le nom demandé ne correspond pas à la même image ZPSI.');
        }
        if ((string) $request['expected_url'] !== (string) wp_get_attachment_url($id)) {
            throw new RuntimeException('Le média a changé depuis le contrôle. Relancez la vérification.');
        }
        if (!is_array($old_meta)) { throw new RuntimeException('Métadonnées image absentes.'); }
        $dir = dirname($source);
        $dest = $dir . '/' . $target_name;
        if (file_exists($dest) || is_link($dest)) { throw new RuntimeException('Le nom de destination existe déjà. Aucun remplacement.'); }
        $map = array($source => $dest);
        $new_meta = $old_meta;
        $relative = ltrim(str_replace('\\', '/', substr($dest, strlen($base))), '/');
        $new_meta['file'] = $relative;
        $old_stem = pathinfo($old_name, PATHINFO_FILENAME);
        $new_stem = pathinfo($target_name, PATHINFO_FILENAME);
        foreach (($old_meta['sizes'] ?? array()) as $size => $info) {
            $name = $info['file'] ?? '';
            if (!$name || basename($name) !== $name) { throw new RuntimeException('Nom de miniature invalide.'); }
            if (strpos($name, $old_stem . '-') !== 0) { continue; }
            $new_name = $new_stem . substr($name, strlen($old_stem));
            $from = $dir . '/' . $name;
            $to = $dir . '/' . $new_name;
            if (is_link($from) || !is_file($from) || file_exists($to) || is_link($to)) { throw new RuntimeException('Miniature absente ou destination déjà utilisée.'); }
            $map[$from] = $to;
            $new_meta['sizes'][$size]['file'] = $new_name;
        }
        foreach ($map as $from => $to) {
            // Keep old URLs valid: retain old files, with no second attachment.
            // A hard link avoids duplicate disk storage when supported.
            if (!@link($from, $to)) {
                $out = @fopen($to, 'x+b');
                if (!$out) { throw new RuntimeException('Impossible de créer le nouveau fichier.'); }
                $created[] = $to;
                $in = @fopen($from, 'rb');
                if (!$in) { fclose($out); throw new RuntimeException('Fichier source illisible.'); }
                $count = stream_copy_to_stream($in, $out);
                fclose($in); fclose($out);
                if ($count !== filesize($from)) { throw new RuntimeException('Copie incomplète.'); }
            } else { $created[] = $to; }
        }
        // Save rollback information before changing the attachment pointers.
        if (!update_post_meta($id, '_zpsi_media_rename_backup', array('attached' => $old_attached, 'metadata' => $old_meta, 'new_file' => $relative))) {
            throw new RuntimeException('Impossible de sauvegarder les métadonnées.');
        }
        $changed = true;
        update_attached_file($id, $dest);
        wp_update_attachment_metadata($id, $new_meta);
        if (get_post_meta($id, '_wp_attached_file', true) !== $relative || wp_get_attachment_metadata($id) !== $new_meta) {
            throw new RuntimeException('Mise à jour des métadonnées incomplète.');
        }
        clean_post_cache($id);
        return array('id' => $id, 'url' => wp_get_attachment_url($id), 'filename' => $target_name, 'renamed' => true);
    } catch (Throwable $e) {
        if ($changed) {
            update_post_meta($id, '_wp_attached_file', $old_attached);
            wp_update_attachment_metadata($id, $old_meta);
            clean_post_cache($id);
            // If rollback cannot be confirmed, retain new files as well.
            if (get_post_meta($id, '_wp_attached_file', true) !== $old_attached || wp_get_attachment_metadata($id) !== $old_meta) {
                return new WP_Error('zpsi_restore', 'Restauration à vérifier ; fichiers conservés. Aucun nouvel envoi.', array('status' => 500));
            }
        }
        foreach ($created as $path) { @unlink($path); }
        return new WP_Error('zpsi_rename_failed', $e->getMessage(), array('status' => 409));
    } finally {
        flock($lock, LOCK_UN); fclose($lock);
    }
}

add_action('rest_api_init', function () {
    register_rest_route('zpsi/v1', '/media/(?P<id>\d+)/rename', array(
        'methods' => 'POST',
        'permission_callback' => function ($request) {
            return current_user_can('upload_files') && current_user_can('edit_post', (int) $request['id']);
        },
        'callback' => 'zpsi_media_rename',
        'args' => array('filename' => array('required' => true, 'type' => 'string'), 'expected_url' => array('required' => true, 'type' => 'string')),
    ));
});
