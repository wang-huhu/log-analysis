import requests
from urllib.parse import quote


class GitLabFileNotFoundError(FileNotFoundError):
    pass


def _normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def get_file(project_id: str, file_path: str, ref: str, token: str, base_url: str) -> dict | None:
    # 读取 GitLab 仓库指定 ref 下的单文件元数据与内容（存在则返回 JSON，不存在返回 None）
    encoded_path = quote(file_path, safe="")
    url = f"{_normalize_base_url(base_url)}/api/v4/projects/{project_id}/repository/files/{encoded_path}"

    try:
        response = requests.get(
            url,
            params={"ref": ref},
            headers={"PRIVATE-TOKEN": token},
            timeout=30,
        )
    except requests.Timeout as exc:
        raise RuntimeError("GitLab 文件接口请求超时") from exc
    except requests.RequestException as exc:
        raise RuntimeError("GitLab 文件接口请求失败") from exc

    if response.status_code == 404:
        return None

    if response.status_code != 200:
        raise RuntimeError(f"GitLab 文件接口返回异常状态码: {response.status_code}")

    return response.json()


def get_first_existing_file(
    candidate_paths: list[str],
    project_id: str,
    ref: str,
    token: str,
    base_url: str,
) -> dict | None:
    # 按候选路径顺序查找第一个真实存在的文件，作为源码上下文入口
    for path in candidate_paths:
        result = get_file(
            project_id=project_id,
            file_path=path,
            ref=ref,
            token=token,
            base_url=base_url,
        )
        if result is not None:
            return result
    return None
