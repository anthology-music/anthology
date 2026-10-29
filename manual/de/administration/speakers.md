# Raumfeld-Lautsprecher

Anthology spielt auf Teufel-Raumfeld-Lautsprechern. Der Server muss den Raumfeld-Host finden, und die Lautsprecher müssen den Server erreichen.

## Den Raumfeld-Host finden

- **Mit Host-Netzwerk** (`Network=host` in `anthology.pod`, `network_mode: host` in Compose) findet der Server den Raumfeld-Host selbst per Multicast (SSDP).
- **Ohne Host-Netzwerk** (der rootless Pod in der Vorgabe) erreicht Multicast den Server nicht. Trage die Adresse des Raumfeld-Hosts unter **Einstellungen › Lautsprecher** ein – die IP-Adresse der Basis oder des Lautsprechers, der als Host dient – oder setze `ANTHOLOGY_RAUMFELD_HOSTS`.

**Einstellungen › Lautsprecher** zeigt jedes System mit seinem Zustand und, wenn es nicht erreichbar ist, den Grund.

## Die Lautsprecher erreichen den Server

Die Lautsprecher holen die Musik per HTTP beim Server. Setze `ANTHOLOGY_OUTPUT_MEDIA_URL` auf die Adresse des Servers, wie die Lautsprecher sie sehen, zum Beispiel `http://192.168.1.10:8400`. Ohne diese Angabe nimmt der Server seine eigene Adresse auf dem Weg zu den Lautsprechern – hinter der Port-Weiterleitung des Pods ist das die Adresse des Containers, also setze die URL dort.

Lautsprecher und Server müssen im selben lokalen Netz sein; zum Internet muss kein Port geöffnet werden.

So spielst du auf Lautsprechern: [Auf Lautsprechern abspielen](/de/guide/speakers).
