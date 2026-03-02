"""
端到端测试脚本
"""
import asyncio
import json
from src.agent.core import run


def _resp(result: dict) -> str:
    """从 run() 返回值中取 response 字符串"""
    return result["response"]


def _tools(result: dict) -> list:
    return result.get("tool_results", [])


async def test_greeting():
    """测试1：问候（0次模型调用）"""
    print("=== 测试1: 问候 ===")
    result = await run("test001", "你好")
    print(f"Response: {_resp(result)[:100]}")
    print()


async def test_simple_query():
    """测试2：单轮简单查询"""
    print("=== 测试2: 单轮简单查询 ===")
    result = await run("test002", "查询两居室房源")
    resp = _resp(result)
    print(f"Response: {resp[:300]}")
    print(f"Tools called: {[t['name'] for t in _tools(result)]}")

    try:
        data = json.loads(resp)
        print(f"Houses found: {len(data.get('houses', []))}: {data.get('houses', [])}")
    except:
        pass
    print()


async def test_complex_query():
    """测试3：单轮复杂查询"""
    print("=== 测试3: 单轮复杂查询 ===")
    result = await run("test003", "帮我找海淀区两居室，预算8000以内，要近地铁，精装修")
    resp = _resp(result)
    print(f"Response: {resp[:300]}")
    print(f"Tools called: {[t['name'] for t in _tools(result)]}")

    try:
        data = json.loads(resp)
        print(f"Houses found: {len(data.get('houses', []))}: {data.get('houses', [])}")
    except:
        pass
    print()


async def test_multi_turn():
    """测试4：多轮对话"""
    print("=== 测试4: 多轮对话 ===")

    # 第一轮
    print("Round 1: 我想在朝阳区找房，预算10000以内")
    r1 = await run("test004", "我想在朝阳区找房，预算10000以内")
    print(f"Response 1: {_resp(r1)[:200]}")
    print(f"Tools called: {[t['name'] for t in _tools(r1)]}")

    # 第二轮
    print("\nRound 2: 要精装修的，而且要有电梯")
    r2 = await run("test004", "要精装修的，而且要有电梯")
    resp2 = _resp(r2)
    print(f"Response 2: {resp2[:200]}")
    print(f"Tools called: {[t['name'] for t in _tools(r2)]}")

    try:
        data = json.loads(resp2)
        print(f"Houses found: {len(data.get('houses', []))}: {data.get('houses', [])}")
    except:
        pass
    print()


async def test_rent_operation():
    """测试5：租房操作"""
    print("=== 测试5: 租房操作 ===")

    # 先查房
    r1 = await run("test005", "查询海淀区的房源")
    resp1 = _resp(r1)
    print(f"Query result: {resp1[:200]}")

    # 提取第一个房源ID
    try:
        data = json.loads(resp1)
        houses = data.get('houses', [])
        if houses:
            house_id = houses[0]
            print(f"\nTrying to rent: {house_id}")
            r2 = await run("test005", f"我想租{house_id}这套")
            resp2 = _resp(r2)
            print(f"Rent result: {resp2[:200]}")
            print(f"Tools called: {[t['name'] for t in _tools(r2)]}")
    except Exception as e:
        print(f"Error: {e}")
    print()


async def main():
    print("=" * 60)
    print("租房 AI Agent 端到端测试")
    print("=" * 60)
    print()

    try:
        await test_greeting()
        await test_simple_query()
        await test_complex_query()
        await test_multi_turn()
        await test_rent_operation()

        print("=" * 60)
        print("测试完成！")
        print("=" * 60)
    except Exception as e:
        print(f"\n[FAIL] 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
